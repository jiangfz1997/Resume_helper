<template>
  <div>
    <n-page-header title="Generate Resume" style="margin-bottom: 20px" />

    <!-- Step indicator -->
    <n-steps :current="currentStep" style="margin-bottom: 24px">
      <n-step title="Job Description" description="Paste the JD text" />
      <n-step title="Review Match" description="Select experiences to include" />
      <n-step title="Edit & Export" description="Refine and download" />
    </n-steps>

    <!-- Stage 1: JD input -->
    <template v-if="stage === 'jd'">
      <n-card title="Job Description">
        <n-input
          v-model:value="jdText"
          type="textarea"
          :rows="12"
          placeholder="Paste the full job description here..."
          style="font-family: monospace; font-size: 13px"
        />
        <n-alert v-if="analyzeError" type="error" style="margin-top: 12px">{{ analyzeError }}</n-alert>
        <template #footer>
          <n-button type="primary" :loading="analyzeLoading" :disabled="!jdText.trim()" @click="runAnalyze">
            Analyze JD
          </n-button>
        </template>
      </n-card>
    </template>

    <!-- Stage 2: Match preview + selection -->
    <template v-if="stage === 'preview' && preview">
      <!-- Match summary -->
      <n-card title="Match Analysis" style="margin-bottom: 16px">
        <n-space align="center" style="margin-bottom: 12px">
          <n-text style="font-size: 16px; font-weight: 600">{{ preview.job_title }}</n-text>
          <n-text depth="3" v-if="preview.company">@ {{ preview.company }}</n-text>
        </n-space>

        <n-space align="center" style="margin-bottom: 16px">
          <n-text depth="3" style="width: 120px">Match Score</n-text>
          <n-progress
            type="line"
            :percentage="matchPct"
            :color="matchPct >= 60 ? '#18a058' : '#f0a020'"
            :rail-color="'#333'"
            style="width: 280px"
          />
          <n-text :type="matchPct >= 60 ? 'success' : 'warning'" style="font-weight: 600">
            {{ matchPct }}%
          </n-text>
        </n-space>

        <n-grid :cols="2" :x-gap="16">
          <n-gi>
            <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 8px">MATCHED SKILLS</n-text>
            <n-space v-if="preview.matched_skills.length" size="small" style="flex-wrap: wrap">
              <n-tag v-for="s in preview.matched_skills" :key="s" type="success" size="small">{{ s }}</n-tag>
            </n-space>
            <n-text v-else depth="3" style="font-size: 12px">— none —</n-text>
          </n-gi>
          <n-gi>
            <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 8px">MISSING SKILLS</n-text>
            <n-space v-if="preview.missing_skills.length" size="small" style="flex-wrap: wrap">
              <n-tag v-for="s in preview.missing_skills" :key="s" type="error" size="small">{{ s }}</n-tag>
            </n-space>
            <n-text v-else depth="3" style="font-size: 12px">— none —</n-text>
          </n-gi>
        </n-grid>

        <n-blockquote v-if="preview.relevance_notes" style="margin-top: 16px; font-size: 13px">
          {{ preview.relevance_notes }}
        </n-blockquote>
      </n-card>

      <!-- Experience selection -->
      <n-card title="Select Work Experiences" style="margin-bottom: 16px">
        <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 12px">
          Highlighted items are recommended by the LLM. Uncheck to exclude.
        </n-text>
        <n-space vertical size="small">
          <n-card
            v-for="(exp, i) in preview.all_experiences"
            :key="i"
            size="small"
            :style="isExpHighlighted(exp) ? 'border-color: #336699' : ''"
          >
            <div style="display: flex; align-items: flex-start; gap: 12px">
              <n-checkbox v-model:checked="selectedExpMap[i]" style="margin-top: 2px" />
              <div style="flex: 1">
                <n-space align="center" size="small">
                  <n-text style="font-size: 14px; font-weight: 500">
                    {{ exp.title }} @ {{ exp.company }}
                  </n-text>
                  <n-tag v-if="isExpHighlighted(exp)" size="tiny" type="info">recommended</n-tag>
                </n-space>
                <n-text depth="3" style="font-size: 12px; display: block; margin-top: 2px">
                  {{ exp.start_date }} — {{ exp.end_date ?? 'present' }}
                </n-text>
                <n-text depth="3" style="font-size: 12px; margin-top: 4px; display: block">
                  {{ exp.description.slice(0, 2).join(' · ') }}
                </n-text>
              </div>
            </div>
          </n-card>
          <n-text v-if="!preview.all_experiences.length" depth="3" style="font-size: 12px">
            No work experiences in profile.
          </n-text>
        </n-space>
      </n-card>

      <!-- Project selection -->
      <n-card title="Select Projects" style="margin-bottom: 16px">
        <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 12px">
          Highlighted items are recommended by the LLM. Uncheck to exclude.
        </n-text>
        <n-space vertical size="small">
          <n-card
            v-for="(proj, i) in preview.all_projects"
            :key="i"
            size="small"
            :style="isProjHighlighted(proj) ? 'border-color: #336699' : ''"
          >
            <div style="display: flex; align-items: flex-start; gap: 12px">
              <n-checkbox v-model:checked="selectedProjMap[i]" style="margin-top: 2px" />
              <div style="flex: 1">
                <n-space align="center" size="small">
                  <n-text style="font-size: 14px; font-weight: 500">{{ proj.name }}</n-text>
                  <n-tag v-if="isProjHighlighted(proj)" size="tiny" type="info">recommended</n-tag>
                </n-space>
                <n-text depth="3" style="font-size: 12px; display: block; margin-top: 2px">
                  {{ proj.description }}
                </n-text>
                <n-space v-if="proj.tech_stack.length" size="small" style="margin-top: 6px">
                  <n-tag v-for="t in proj.tech_stack" :key="t" size="tiny" type="default">{{ t }}</n-tag>
                </n-space>
              </div>
            </div>
          </n-card>
          <n-text v-if="!preview.all_projects.length" depth="3" style="font-size: 12px">
            No projects in profile.
          </n-text>
        </n-space>
      </n-card>

      <!-- Template selection -->
      <n-card title="Resume Template (optional)" style="margin-bottom: 16px">
        <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 12px">
          Choose a template to control the LaTeX layout. Leave unselected to use the default style.
        </n-text>
        <n-spin v-if="templateLoading" />
        <n-space v-else wrap size="small">
          <div
            v-for="t in allTemplates"
            :key="t.id"
            :style="selectedTemplateId === t.id
              ? 'padding:8px 14px;border:1px solid #7eb8f7;border-radius:6px;cursor:pointer;background:#1a2a3a'
              : 'padding:8px 14px;border:1px solid #2e2e2e;border-radius:6px;cursor:pointer'"
            @click="toggleTemplate(t)"
          >
            <n-text style="font-size: 13px; font-weight: 500">{{ t.name }}</n-text>
            <n-tag
              :type="t.source === 'global' ? 'info' : 'default'"
              size="tiny"
              style="margin-left: 6px"
            >{{ t.source }}</n-tag>
            <div v-if="t.industry || t.style_tag" style="font-size: 11px; color: #888; margin-top: 2px">
              {{ [t.industry, t.style_tag].filter(Boolean).join(' · ') }}
            </div>
          </div>
          <div v-if="allTemplates.length === 0" style="color: #888; font-size: 12px">
            No templates found. Upload one in the Templates tab.
          </div>
        </n-space>
        <n-button
          v-if="selectedTemplateId"
          size="tiny"
          quaternary
          style="margin-top: 8px"
          @click="selectedTemplateId = null; selectedTemplateSource = undefined"
        >
          Clear selection
        </n-button>
      </n-card>

      <!-- Pipeline config -->
      <n-card title="Pipeline Config" style="margin-bottom: 16px">
        <n-grid :cols="4" :x-gap="12">
          <n-gi>
            <n-form-item label="Initial Threshold" label-placement="top">
              <n-input-number v-model:value="config.initial_threshold" :min="0" :max="1" :step="0.05" size="small" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="Decay / Retry" label-placement="top">
              <n-input-number v-model:value="config.decay_per_retry" :min="0" :max="0.5" :step="0.01" size="small" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="Min Threshold" label-placement="top">
              <n-input-number v-model:value="config.min_threshold" :min="0" :max="1" :step="0.05" size="small" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="Max Retries" label-placement="top">
              <n-input-number v-model:value="config.max_retries" :min="1" :max="10" :step="1" size="small" />
            </n-form-item>
          </n-gi>
        </n-grid>
      </n-card>

      <n-space>
        <n-button @click="stage = 'jd'">Back</n-button>
        <n-button type="primary" :loading="generateLoading" @click="runGenerate">
          Generate Resume with Selected
        </n-button>
      </n-space>
      <n-alert v-if="generateError" type="error" style="margin-top: 12px">{{ generateError }}</n-alert>
    </template>

    <!-- Stage 3: Structured draft editor -->
    <template v-if="stage === 'result' && draft">
      <!-- Action bar -->
      <n-card style="margin-bottom: 16px">
        <n-space align="center" justify="space-between">
          <n-space align="center">
            <n-text style="font-size: 15px; font-weight: 600">Resume Draft</n-text>
            <n-tag type="default" size="small">editable</n-tag>
          </n-space>
          <n-space>
            <n-button size="small" @click="reset" quaternary>Start Over</n-button>
            <n-button
              v-if="currentSessionId"
              size="small"
              :loading="saveLoading"
              @click="saveDraft"
            >Save</n-button>
            <n-button size="small" :loading="renderLoading" @click="getLatex">Get LaTeX</n-button>
            <n-button size="small" type="primary" :loading="renderLoading" @click="renderPdf">
              Render PDF
            </n-button>
          </n-space>
        </n-space>
        <n-alert v-if="renderError" type="error" style="margin-top: 12px">{{ renderError }}</n-alert>
      </n-card>

      <!-- Keyword coverage (after generation) -->
      <n-card v-if="kwAfterPct > 0 || reqAfterPct > 0" title="Keyword Coverage" style="margin-bottom: 16px">
        <n-space align="center" style="margin-bottom: 8px">
          <n-text depth="3" style="width: 120px">Weighted Score</n-text>
          <n-progress type="line" :percentage="kwAfterPct" :color="kwAfterPct >= 60 ? '#18a058' : '#f0a020'" :rail-color="'#333'" style="width: 280px" />
          <n-text :type="kwAfterPct >= 60 ? 'success' : 'warning'" style="font-weight: 600">{{ kwAfterPct }}%</n-text>
        </n-space>
        <n-space align="center">
          <n-text depth="3" style="width: 120px">Required Keywords</n-text>
          <n-progress type="line" :percentage="reqAfterPct" :color="reqAfterPct >= 60 ? '#18a058' : '#d03050'" :rail-color="'#333'" style="width: 280px" />
          <n-text :type="reqAfterPct >= 60 ? 'success' : 'error'" style="font-weight: 600">{{ reqAfterPct }}%</n-text>
        </n-space>
      </n-card>

      <!-- Summary -->
      <n-card style="margin-bottom: 16px">
        <template #header>
          <n-space align="center" justify="space-between">
            <span>Summary</span>
            <n-button size="tiny" quaternary @click="openComment('summary', 'Summary')">Comment</n-button>
          </n-space>
        </template>
        <n-input
          v-model:value="draft.summary"
          type="textarea"
          :rows="4"
          placeholder="Professional summary..."
        />
      </n-card>

      <!-- Experiences -->
      <n-card title="Work Experience" style="margin-bottom: 16px">
        <n-collapse>
          <n-collapse-item
            v-for="(exp, ei) in draft.experiences"
            :key="ei"
            :name="String(ei)"
          >
            <template #header>
              <n-space align="center" size="small" style="width: 100%; justify-content: space-between">
                <n-space align="center" size="small">
                  <n-text style="font-size: 13px; font-weight: 500">
                    {{ exp.title }} @ {{ exp.company }}
                  </n-text>
                  <n-text depth="3" style="font-size: 12px">
                    {{ exp.start_date }} — {{ exp.end_date ?? 'present' }}
                  </n-text>
                </n-space>
                <n-button
                  size="tiny"
                  quaternary
                  @click.stop="openComment(`experiences[${ei}]`, `${exp.title} @ ${exp.company}`)"
                >
                  Comment
                </n-button>
              </n-space>
            </template>

            <n-grid :cols="3" :x-gap="12" style="margin-bottom: 12px">
              <n-gi>
                <n-form-item label="Title" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="exp.title" size="small" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="Company" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="exp.company" size="small" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="Location" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="exp.location" size="small" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="Start Date" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="exp.start_date" size="small" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="End Date" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="exp.end_date" size="small" placeholder="present" />
                </n-form-item>
              </n-gi>
            </n-grid>

            <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 8px">BULLETS</n-text>
            <n-space vertical size="small">
              <div
                v-for="(bullet, bi) in exp.bullets"
                :key="bi"
                style="display: flex; align-items: flex-start; gap: 8px"
              >
                <n-checkbox
                  v-model:checked="bullet.highlighted"
                  title="Highlight this bullet"
                  style="margin-top: 6px; flex-shrink: 0"
                />
                <n-input
                  v-model:value="bullet.text"
                  type="textarea"
                  :rows="2"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  size="small"
                  style="flex: 1"
                />
                <n-button
                  size="tiny"
                  quaternary
                  type="error"
                  style="margin-top: 4px; flex-shrink: 0"
                  @click="exp.bullets.splice(bi, 1)"
                >
                  Del
                </n-button>
              </div>
              <n-button
                size="tiny"
                dashed
                @click="exp.bullets.push({ text: '', highlighted: false })"
              >
                + Add bullet
              </n-button>
            </n-space>
          </n-collapse-item>
        </n-collapse>
        <n-text v-if="!draft.experiences.length" depth="3" style="font-size: 12px">
          No experiences.
        </n-text>
      </n-card>

      <!-- Education -->
      <n-card title="Education" style="margin-bottom: 16px">
        <n-space vertical size="small">
          <n-card
            v-for="(edu, i) in draft.education"
            :key="i"
            size="small"
          >
            <n-grid :cols="3" :x-gap="12">
              <n-gi>
                <n-form-item label="Institution" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="edu.institution" size="small" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="Degree" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="edu.degree" size="small" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="Field of Study" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="edu.field_of_study" size="small" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="Start Date" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="edu.start_date" size="small" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="End Date" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="edu.end_date" size="small" placeholder="present" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="GPA" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="edu.gpa" size="small" placeholder="optional" />
                </n-form-item>
              </n-gi>
            </n-grid>
          </n-card>
          <n-text v-if="!draft.education.length" depth="3" style="font-size: 12px">
            No education records.
          </n-text>
        </n-space>
      </n-card>

      <!-- Projects -->
      <n-card title="Projects" style="margin-bottom: 16px">
        <n-collapse>
          <n-collapse-item
            v-for="(proj, pi) in draft.projects"
            :key="pi"
            :name="String(pi)"
          >
            <template #header>
              <n-space align="center" size="small" style="width: 100%; justify-content: space-between">
                <n-text style="font-size: 13px; font-weight: 500">{{ proj.name }}</n-text>
                <n-button
                  size="tiny"
                  quaternary
                  @click.stop="openComment(`projects[${pi}]`, proj.name)"
                >
                  Comment
                </n-button>
              </n-space>
            </template>

            <n-grid :cols="2" :x-gap="12" style="margin-bottom: 12px">
              <n-gi>
                <n-form-item label="Name" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="proj.name" size="small" />
                </n-form-item>
              </n-gi>
              <n-gi>
                <n-form-item label="URL" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="proj.url" size="small" placeholder="optional" />
                </n-form-item>
              </n-gi>
              <n-gi :span="2">
                <n-form-item label="Description" label-placement="top" :show-feedback="false">
                  <n-input v-model:value="proj.description" type="textarea" :rows="2" size="small" />
                </n-form-item>
              </n-gi>
            </n-grid>

            <n-space size="small" style="flex-wrap: wrap; margin-bottom: 12px">
              <n-tag
                v-for="(tech, ti) in proj.tech_stack"
                :key="ti"
                size="small"
                closable
                @close="proj.tech_stack.splice(ti, 1)"
              >
                {{ tech }}
              </n-tag>
            </n-space>

            <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 8px">BULLETS</n-text>
            <n-space vertical size="small">
              <div
                v-for="(bullet, bi) in proj.bullets"
                :key="bi"
                style="display: flex; align-items: flex-start; gap: 8px"
              >
                <n-checkbox
                  v-model:checked="bullet.highlighted"
                  title="Highlight this bullet"
                  style="margin-top: 6px; flex-shrink: 0"
                />
                <n-input
                  v-model:value="bullet.text"
                  type="textarea"
                  :rows="2"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  size="small"
                  style="flex: 1"
                />
                <n-button
                  size="tiny"
                  quaternary
                  type="error"
                  style="margin-top: 4px; flex-shrink: 0"
                  @click="proj.bullets.splice(bi, 1)"
                >
                  Del
                </n-button>
              </div>
              <n-button
                size="tiny"
                dashed
                @click="proj.bullets.push({ text: '', highlighted: false })"
              >
                + Add bullet
              </n-button>
            </n-space>
          </n-collapse-item>
        </n-collapse>
        <n-text v-if="!draft.projects.length" depth="3" style="font-size: 12px">
          No projects.
        </n-text>
      </n-card>

      <!-- Skills -->
      <n-card title="Skills" style="margin-bottom: 16px">
        <n-space wrap size="small">
          <n-tag
            v-for="(skill, si) in draft.skills"
            :key="si"
            :type="proficiencyType(skill.proficiency)"
            size="small"
          >
            {{ skill.category }}: {{ skill.name }}
          </n-tag>
        </n-space>
        <n-text v-if="!draft.skills.length" depth="3" style="font-size: 12px">No skills.</n-text>
      </n-card>

      <!-- Bottom actions -->
      <n-space style="margin-bottom: 32px">
        <n-button @click="stage = 'preview'" :disabled="renderLoading">Back to Selection</n-button>
        <n-button :loading="renderLoading" @click="getLatex">Get LaTeX Source</n-button>
        <n-button type="primary" :loading="renderLoading" @click="renderPdf">Render PDF</n-button>
      </n-space>
      <ChatPanel
        v-if="currentSessionId"
        :session-id="currentSessionId"
        :draft="draft"
        :pending-scope-init="pendingScope ?? undefined"
        @patch="handlePatch"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { analyzeJD, confirmGenerate, getSession, listTemplates, renderDraft, updateSessionDraft } from '../api/client'
import type {
  ChatScope,
  Education,
  MatchingPreview,
  PipelineConfig,
  Project,
  ResumePatch,
  TailoredResumeDraft,
  TemplateRead,
  WorkExperience,
} from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useEditorStore } from '../stores/editor'
import { useRouter, useRoute } from 'vue-router'
import ChatPanel from '../components/ChatPanel.vue'

const auth = useAuthStore()
const editorStore = useEditorStore()
const router = useRouter()
const route = useRoute()
const message = useMessage()
const token = () => auth.token!

const currentSessionId = ref<string | null>(null)

type Stage = 'jd' | 'preview' | 'result'
const stage = ref<Stage>('jd')
const currentStep = computed(() => stage.value === 'jd' ? 1 : stage.value === 'preview' ? 2 : 3)

// ── stage 1 ────────────────────────────────────────────────────
const jdText = ref(`We are looking for a Senior Backend Engineer to join our platform team.

Requirements:
- 4+ years of experience in Python backend development
- Strong experience with FastAPI or Django REST Framework
- Proficiency in PostgreSQL and Redis
- Experience with Docker and Kubernetes
- Familiarity with LLM tooling (LangChain, OpenAI API) is a strong plus

Soft skills: strong communication, collaborative mindset, proactive problem-solving.`)

const analyzeLoading = ref(false)
const analyzeError = ref('')

async function runAnalyze(): Promise<void> {
  analyzeError.value = ''
  analyzeLoading.value = true
  try {
    const data = await analyzeJD(token(), jdText.value)
    currentSessionId.value = data.session_id
    preview.value = data
    initSelections(data)
    stage.value = 'preview'
  } catch (e) {
    analyzeError.value = (e as Error).message
  } finally {
    analyzeLoading.value = false
  }
}

// ── templates ──────────────────────────────────────────────────
const allTemplates = ref<TemplateRead[]>([])
const templateLoading = ref(false)
const selectedTemplateId = ref<string | null>(null)
const selectedTemplateSource = ref<'global' | 'user' | undefined>(undefined)

onMounted(async () => {
  templateLoading.value = true
  try { allTemplates.value = await listTemplates(token()) } finally { templateLoading.value = false }

  const sid = route.query.session_id as string | undefined
  if (sid) {
    await loadSessionById(sid)
  }
})

async function loadSessionById(sid: string): Promise<void> {
  try {
    const detail = await getSession(token(), sid)
    currentSessionId.value = sid
    if (detail.status === 'draft_ready' && detail.tailored_draft) {
      draft.value = detail.tailored_draft
      kwAfterPct.value = Math.round(detail.keyword_coverage * 100)
      reqAfterPct.value = Math.round(detail.required_coverage * 100)
      stage.value = 'result'
    } else if (detail.status === 'analyzed' || detail.status === 'generating') {
      const p: MatchingPreview = {
        session_id: sid,
        match_score: detail.match_score ?? 0,
        job_title: detail.job_title ?? '',
        company: detail.company,
        matched_skills: detail.matched_skills,
        missing_skills: detail.missing_skills,
        highlighted_experiences: detail.highlighted_experiences,
        all_experiences: detail.all_experiences,
        all_projects: detail.all_projects,
        relevance_notes: detail.relevance_notes,
        keyword_coverage: detail.keyword_coverage,
        required_coverage: detail.required_coverage,
      }
      preview.value = p
      initSelections(p)
      jdText.value = detail.jd_text
      stage.value = 'preview'
    }
  } catch {
    // silently ignore — start fresh
  }
}

function toggleTemplate(t: TemplateRead): void {
  if (selectedTemplateId.value === t.id) {
    selectedTemplateId.value = null
    selectedTemplateSource.value = undefined
  } else {
    selectedTemplateId.value = t.id
    selectedTemplateSource.value = t.source
  }
}

// ── stage 2 ────────────────────────────────────────────────────
const preview = ref<MatchingPreview | null>(null)
const selectedExpMap = reactive<Record<number, boolean>>({})
const selectedProjMap = reactive<Record<number, boolean>>({})

const config = reactive<PipelineConfig>({
  initial_threshold: 0.8,
  decay_per_retry: 0.05,
  min_threshold: 0.6,
  max_retries: 3,
})

const matchPct = computed(() => preview.value ? Math.round(preview.value.match_score * 100) : 0)

const kwAfterPct = ref(0)
const reqAfterPct = ref(0)

const highlightedSet = computed(() => {
  return new Set((preview.value?.highlighted_experiences ?? []).map(s => s.toLowerCase()))
})

function isExpHighlighted(exp: WorkExperience): boolean {
  const company = exp.company.toLowerCase()
  for (const h of highlightedSet.value) {
    if (h.includes(company) || company.includes(h)) return true
  }
  return false
}

function isProjHighlighted(proj: Project): boolean {
  const name = proj.name.toLowerCase()
  for (const h of highlightedSet.value) {
    if (h.includes(name) || name.includes(h)) return true
  }
  return false
}

function initSelections(data: MatchingPreview): void {
  data.all_experiences.forEach((exp, i) => {
    selectedExpMap[i] = isExpHighlighted(exp)
  })
  data.all_projects.forEach((proj, i) => {
    selectedProjMap[i] = isProjHighlighted(proj)
  })
}

const generateLoading = ref(false)
const generateError = ref('')

async function runGenerate(): Promise<void> {
  if (!preview.value) return
  generateError.value = ''

  const expIndices = Object.entries(selectedExpMap)
    .filter(([, v]) => v)
    .map(([k]) => Number(k))

  const projIndices = Object.entries(selectedProjMap)
    .filter(([, v]) => v)
    .map(([k]) => Number(k))

  generateLoading.value = true
  try {
    const data = await confirmGenerate(
      token(),
      preview.value.session_id,
      expIndices,
      projIndices,
      { ...config },
      selectedTemplateId.value ?? undefined,
      selectedTemplateSource.value,
    )
    draft.value = data
    stage.value = 'result'
    if (preview.value) currentSessionId.value = preview.value.session_id
    try {
      const detail = await getSession(token(), preview.value!.session_id)
      kwAfterPct.value = Math.round(detail.keyword_coverage * 100)
      reqAfterPct.value = Math.round(detail.required_coverage * 100)
    } catch { /* non-critical */ }
  } catch (e) {
    generateError.value = (e as Error).message
  } finally {
    generateLoading.value = false
  }
}

// ── stage 3 ────────────────────────────────────────────────────
const draft = ref<TailoredResumeDraft | null>(null)
const renderLoading = ref(false)
const renderError = ref('')
const saveLoading = ref(false)
const pendingScope = ref<ChatScope | null>(null)

function openComment(path: string, label: string): void {
  pendingScope.value = { path, label }
  chatOpen.value = true
}

function handlePatch(patch: ResumePatch): void {
  if (!draft.value) return
  if (patch.path === 'summary') {
    draft.value.summary = patch.updated_value as string
    return
  }
  const m = patch.path.match(/^(experiences|projects)\[(\d+)\]$/)
  if (m) {
    const field = m[1] as 'experiences' | 'projects'
    const idx = parseInt(m[2])
    ;(draft.value[field] as unknown[])[idx] = patch.updated_value
  }
}

async function saveDraft(): Promise<void> {
  if (!draft.value || !currentSessionId.value) return
  saveLoading.value = true
  try {
    await updateSessionDraft(token(), currentSessionId.value, draft.value)
    message.success('Draft saved')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saveLoading.value = false
  }
}

function proficiencyType(p: string): 'success' | 'warning' | 'default' {
  return p === 'expert' ? 'success' : p === 'intermediate' ? 'warning' : 'default'
}

async function renderPdf(): Promise<void> {
  if (!draft.value) return
  renderError.value = ''
  renderLoading.value = true
  try {
    const blob = await renderDraft(
      token(),
      draft.value,
      true,
      draft.value.template_id ?? selectedTemplateId.value,
      draft.value.template_source ?? selectedTemplateSource.value,
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'resume.pdf'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    renderError.value = (e as Error).message
  } finally {
    renderLoading.value = false
  }
}

async function getLatex(): Promise<void> {
  if (!draft.value) return
  renderError.value = ''
  renderLoading.value = true
  try {
    const blob = await renderDraft(
      token(),
      draft.value,
      false,
      draft.value.template_id ?? selectedTemplateId.value,
      draft.value.template_source ?? selectedTemplateSource.value,
    )
    const text = await blob.text()
    editorStore.setContent(text)
    router.push('/editor')
  } catch (e) {
    renderError.value = (e as Error).message
  } finally {
    renderLoading.value = false
  }
}

function reset(): void {
  stage.value = 'jd'
  preview.value = null
  draft.value = null
  currentSessionId.value = null
  analyzeError.value = ''
  generateError.value = ''
  renderError.value = ''
  selectedTemplateId.value = null
  selectedTemplateSource.value = undefined
  pendingScope.value = null
  kwAfterPct.value = 0
  reqAfterPct.value = 0
}
</script>

