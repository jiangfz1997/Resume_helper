# Resume Tailoring Assistant — Architecture v2

> 记录从"LLM 直出 LaTeX"到"JSON 中心 + Jinja2 渲染"的架构重设计。
> 最后更新：2026-03-14

---

## 核心设计原则

```
LLM 层      只输出 JSON（内容语义，不碰 LaTeX）
用户层      图形化编辑 JSON（字段级修改）
AI 辅助层   局部润色单个 JSON 字段（区域修改）
渲染层      Jinja2 把 JSON 注入 .tex 模板
编译层      tectonic .tex → PDF
```

**LaTeX 是渲染产物，不是数据格式。前后端永远只传 JSON。**

---

## 整体数据流

```
┌─────────────────────────────────────────────────────┐
│  Stage 1: Analyze（已有，不变）                      │
│  POST /resume/analyze                                │
│  JD text → OllamaJDAnalyzer → OllamaSkillMatcher    │
│  → MatchingPreview (JSON) + session_id               │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│  Stage 2: Confirm & Draft Generation（重构）         │
│  POST /resume/confirm                                │
│  session_id + selected exp/proj + template_id        │
│  → OllamaContentDrafter (JSON only)                  │
│  → TailoredResumeDraft (JSON)        ← 返回前端      │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│  Stage 3: 前端图形化编辑（新）                        │
│  用户在表单里直接改字段                               │
│  或点击"✨ 润色"触发局部 AI 改写                      │
│  POST /resume/refine  (单字段 AI 润色)               │
│  ← 返回单个字段的新值，前端局部替换                   │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│  Stage 4: Render + Compile（重构）                   │
│  POST /resume/render                                 │
│  TailoredResumeDraft + template_id                   │
│  → latex_escape + Jinja2.render() → .tex             │
│  → tectonic → PDF (binary)                          │
└─────────────────────────────────────────────────────┘
```

---

## 新增 / 修改的数据模型

### TailoredBullet
```python
class TailoredBullet(BaseModel):
    text: str
    highlighted: bool = False  # LLM 标记为与 JD 高度匹配
```

### TailoredExperience
```python
class TailoredExperience(BaseModel):
    company: str
    title: str
    location: str
    start_date: str
    end_date: Optional[str]
    bullets: list[TailoredBullet]
```

### TailoredProject
```python
class TailoredProject(BaseModel):
    name: str
    description: str
    tech_stack: list[str]
    url: Optional[str]
    bullets: list[TailoredBullet]  # 拆出 bullets，支持逐条润色
```

### TailoredResumeDraft（核心枢纽模型）
```python
class TailoredResumeDraft(BaseModel):
    summary: str
    experiences: list[TailoredExperience]
    education: list[Education]        # 复用现有模型
    projects: list[TailoredProject]
    skills: list[Skill]               # 复用现有模型
    template_id: Optional[uuid.UUID]
    template_source: Optional[Literal["global", "user"]]
```

### RefineRequest（局部润色）
```python
class RefineRequest(BaseModel):
    field_type: Literal["summary", "bullet", "project_description"]
    current_value: str
    context: str                      # 公司名/职位/项目名，帮助 LLM 理解背景
    jd_keywords: list[str]            # 来自 MatchingReport.core_keywords
    instruction: Optional[str] = None # 用户自定义指令，如"更简洁"

class RefineResponse(BaseModel):
    refined_value: str
```

### RenderRequest
```python
class RenderRequest(BaseModel):
    draft: TailoredResumeDraft
    compile: bool = True              # True: 直接返回 PDF；False: 返回 .tex 字符串
```

---

## API 变更

| 端点 | 变更 | 说明 |
|---|---|---|
| `POST /resume/analyze` | 不变 | 返回 `MatchingPreview` |
| `POST /resume/confirm` | **返回值改为** `TailoredResumeDraft` | LLM 只输出 JSON，不生成 LaTeX |
| `POST /resume/render` | **新增** | JSON → Jinja2 → .tex → PDF |
| `POST /resume/refine` | **新增** | 单字段 AI 润色 |
| `POST /resume/compile` | 保留（给高级用户直接提交 .tex） | 不变 |
| `POST /resume/generate` | 保留（legacy，不推荐） | 不变 |

---

## 模板系统（双轨制）

### Global Templates — Jinja2 模式（高可靠）

- 开发者预先手写 `.tex.j2` 文件，本地编译测试通过后入库
- DB 存储：`template_type = 'jinja2'`，`preamble` 字段存完整 Jinja2 模板（含 body）
- 渲染时：`TemplateFiller.render(draft, jinja2_template)` 直接产出 `.tex`
- 编译成功率 ≈ 99%（LLM 从不接触 LaTeX）

Jinja2 分隔符配置（避免与 LaTeX `{}` 冲突）：
```python
jinja2.Environment(
    variable_start_string='<<',
    variable_end_string='>>',
    block_start_string='<%',
    block_end_string='%>',
)
```

模板片段示例：
```latex
\resumeSubheading
  {<< exp.company | latex_escape >>}
  {<< exp.title | latex_escape >>}
  {<< exp.location | latex_escape >>}
  {<< exp.start_date >>~--~<< exp.end_date | default('Present') >>}
\begin{itemize}
  <% for bullet in exp.bullets %>
  \resumeItem{<< bullet.text | latex_escape >>}
  <% endfor %>
\end{itemize}
```

`latex_escape` 为自定义 Jinja2 filter，转义 `& % $ # _ ~ ^ \` 等字符。

### User Templates — Raw 模式（实验性）

- 用户上传 `.tex` 文件，前端拆分为 `preamble` + `body_example`
- DB 存储：`template_type = 'raw'`
- 渲染时：走现有的 LLM 填充路径（body_example 作语法参考），标注"实验性"
- 后续可升级：上传时调用一次 LLM 将 `body_example` 转成 Jinja2 变量格式，自动升级为 Jinja2 模式

### DB 新增字段

```sql
ALTER TABLE global_templates ADD COLUMN template_type VARCHAR(10) DEFAULT 'jinja2';
ALTER TABLE user_templates   ADD COLUMN template_type VARCHAR(10) DEFAULT 'raw';
```

---

## 新增服务组件

### TemplateFiller（纯工程，无 LLM）

```python
class TemplateFiller:
    def __init__(self, template_content: str) -> None:
        env = jinja2.Environment(
            variable_start_string='<<',
            variable_end_string='>>',
            block_start_string='<%',
            block_end_string='%>',
        )
        env.filters['latex_escape'] = latex_escape
        self._tmpl = env.from_string(template_content)

    def render(self, draft: TailoredResumeDraft) -> str:
        return self._tmpl.render(draft.model_dump())
```

### OllamaContentDrafter（新 LLM Agent，替换 OllamaResumeGenerator）

- 只输出 `TailoredResumeDraft` JSON
- Prompt 不含任何 LaTeX 相关内容
- 职责：选排序 + 写 summary + 标记 highlighted bullets
- 解析器：`JsonOutputParser` → Pydantic 验证

### OllamaBulletRefiner（新 LLM Agent）

- 极小 context：单条 bullet / summary / project description
- Prompt：`给定职位背景和 JD 关键词，改写下列文字，保持事实不变，突出 {keywords}，{instruction}`
- 返回纯字符串，无 JSON 包装

---

## 前端界面（GenerateView 重构）

### Stage 2 结果展示（现在：LaTeX 代码块）→（新：结构化表单）

```
┌─ Summary ─────────────────────────────────────────────┐
│ [文本框] Senior Backend Engineer with 5 years...  [✨] │
└───────────────────────────────────────────────────────┘

┌─ Work Experience ──────────────────────── [↕ 拖拽排序] ┐
│ ▼ Google — Software Engineer  2021-01 ~ Present        │
│   ☑ Built distributed systems serving 10M+ users  [✨] │
│   ☑ Led migration to microservices, reduced latency [✨]│
│   ☐ Mentored 3 junior engineers                   [✨] │
│   [+ 添加 bullet]                                      │
│ ▶ Meta — Backend Intern  2020-06 ~ 2020-09             │
└───────────────────────────────────────────────────────┘

┌─ Projects ─────────────────────────────────────────────┐
│ ...                                                    │
└───────────────────────────────────────────────────────┘

[ 选择模板 ▼ ]    [ Generate PDF ]    [ Preview .tex ]
```

**✨ 润色按钮行为：**
1. 前端抓取字段路径 + 当前值 + 上下文
2. `POST /resume/refine` → 返回新值
3. 前端局部替换该字段（Vue reactive 自动更新）
4. 若用户开启"自动预览"，触发 `POST /resume/render`

### 保留 LaTeX Editor（`/editor`）

高级用户仍可从 `TailoredResumeDraft` → render → 在 Monaco 里手动改 `.tex`。
Generate 页面的"Open in LaTeX Editor"按钮保留，改为先 render 再跳转。

---

## LangGraph Pipeline 变更

### 新 generation graph（有 Jinja2 模板时）

```
generate_draft (OllamaContentDrafter → TailoredResumeDraft JSON)
      ↓
render (TemplateFiller.render → .tex)
      ↓
audit (OllamaResumeAuditor，不变)
      ↓
[approved?] → END / → generate_draft (带 feedback)
```

### 无模板时（兜底）

```
generate_draft (OllamaContentDrafter → JSON)
      ↓
render_default (article class 默认模板)
      ↓
audit → END
```

### _GraphState 新增字段

```python
tailored_draft: Optional[TailoredResumeDraft]
rendered_tex: Optional[str]
```

---

## 实现顺序（推荐）

1. **模型层**：新增 `TailoredResumeDraft`、`RefineRequest`、`RenderRequest`
2. **TemplateFiller 服务**：Jinja2 环境 + `latex_escape` filter
3. **手写 2-3 个 Global Jinja2 模板**（.tex.j2），本地编译验证
4. **OllamaContentDrafter agent**：新 prompt，只输出 JSON
5. **API 层**：`/resume/confirm` 改返回类型；新增 `/resume/render`、`/resume/refine`
6. **Pipeline graph 改造**：条件分支（Jinja2 模式 vs 兜底模式）
7. **前端 GenerateView**：结构化表单 + ✨ 润色按钮
8. **DB migration**：`template_type` 字段

---

## 与现有代码的兼容策略

| 现有组件 | 处理方式 |
|---|---|
| `OllamaResumeGenerator` | 保留（legacy `/resume/generate` 路由使用） |
| `OllamaResumeAuditor` | 不变，audit 阶段复用 |
| `TectonicCompiler` | 不变，`/resume/compile` 和 `/resume/render` 都调用它 |
| `TemplatesView.vue` | 不变，上传逻辑不变 |
| `LatexEditorView.vue` | 不变，作为高级模式入口 |
| `user_templates` 表 | 不变，加 `template_type='raw'` 字段即可 |
| `global_templates` 表 | 加 `template_type='jinja2'` 字段，`preamble` 存完整 Jinja2 模板 |

---

## 暂不实现（已记录，防止遗忘）

### 浮窗对话框 Agent

用户可划词选中简历内容，在浮窗里对话让 agent 做修改（局部或全局）。

- 入口：`POST /resume/chat`，input = draft + 对话历史 + 选中文本(可选) + 用户消息
- Agent 先做意图路由（局部 patch / 全局 regenerate），再执行并返回 patch
- 选中文本 + 字段路径（如 `experiences[1]`）作为 system context

### 单 Experience 独立生成接口（为对话框预留）

```
POST /resume/refine-experience
Input:  TailoredExperience + jd_keywords + matched_skills + instruction
Output: TailoredExperience（refined）
```

无 session，无 graph，独立 LLM 调用。前端 `draft.experiences[i] = response` 后触发 render。

---

## 未来扩展点

- **AI 排版调整**：Jinja2 模板暴露排版变量（`<< config.font_size >>`、`<< config.columns >>`），AI 只需输出 `{ "font_size": 11 }` 即可驱动排版
- **模板自动升级**：用户上传 raw 模板后，后台任务将 body_example 转成 Jinja2 格式
- **流式润色**：`/resume/refine` 改成 SSE，边生成边展示
- **简历历史**：存 `TailoredResumeDraft` JSON（轻量），随时 render 成任意模板
- **多语言**：`latex_escape` 加 CJK 字符处理，模板加 `xeCJK` package
