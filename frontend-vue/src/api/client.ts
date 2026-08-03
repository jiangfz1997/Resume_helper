const BASE = '/api'

export interface CategoryMatchResult {
  total: number
  matched: number
  missing: string[]
}

export interface KeywordMatchResult {
  score: number
  tech_required: CategoryMatchResult
  tech_preferred: CategoryMatchResult
  nice_to_have: CategoryMatchResult
  matched_keywords: string[]
  missing_keywords: string[]
  tech_keywords?: CategoryMatchResult
  preferred_qualifications?: CategoryMatchResult
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  const r = await fetch(BASE + path, { ...options, headers })
  if (!r.ok) {
    if (r.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/auth'
    }
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new ApiError(r.status, err.detail ?? JSON.stringify(err))
  }
  if (r.status === 204 || r.headers.get('content-length') === '0') {
    return undefined as T
  }
  return r.json() as Promise<T>
}

// ── types ──────────────────────────────────────────────────────

export interface UserCreate { full_name: string; email: string; password: string }
export interface UserRead { id: string; email: string; full_name: string; created_at: string }

export interface ContactInfo {
  email?: string
  phone?: string
  location?: string
  linkedin?: string
  github?: string
  website?: string
}

export interface WorkExperience {
  company: string
  title: string
  start_date: string
  end_date?: string
  description: string[]
}

export interface Education {
  institution: string
  degree: string
  field_of_study: string
  start_date: string
  end_date?: string
  gpa?: string
}

export interface Project {
  name: string
  description: string
  bullets: string[]
  tech_stack: string[]
  url?: string
}

export type ProficiencyLevel = 'expert' | 'intermediate' | 'beginner'

export interface Skill { category: string; name: string; proficiency: ProficiencyLevel }

export interface MasterProfile {
  user_id: string
  full_name: string
  summary?: string
  contact_info?: ContactInfo
  work_experiences: WorkExperience[]
  educations: Education[]
  projects: Project[]
  skills: Skill[]
}

export interface ProfileUpdate {
  summary?: string
  contact_info?: ContactInfo
  work_experiences?: WorkExperience[]
  educations?: Education[]
  projects?: Project[]
}

export interface UnclassifiedSection {
  title: string
  content: string[]
}

export interface ParsedProfileDraft {
  work_experiences: WorkExperience[]
  educations: Education[]
  projects: Project[]
  skills: Skill[]
  summary?: string
  unclassified_sections?: UnclassifiedSection[]
}

export interface PipelineConfig {
  initial_threshold: number
  decay_per_retry: number
  min_threshold: number
  max_retries: number
}

export interface QualificationResult {
  item: string
  matched: boolean
  reason: string
}

export interface SkillGapSuggestion {
  missing_keyword: string
  covered_by: string[]
}

export interface MatchingPreview {
  session_id: string
  match_score: number
  job_title: string
  company?: string
  matched_skills: string[]
  missing_skills: string[]
  highlighted_experience_indices: number[]
  highlighted_project_indices: number[]
  topn_experience_indices: number[]
  topn_project_indices: number[]
  all_experiences: WorkExperience[]
  all_projects: Project[]
  relevance_notes: string
  qualification_details?: QualificationResult[]
  kw_detail?: KeywordMatchResult
  skill_gap_suggestions?: SkillGapSuggestion[]
}

export interface ResumeResponse {
  latex_content: string
  score: number
  retries: number
  status: 'approved' | 'max_retries_reached' | 'in_progress'
}

export interface TailoredBullet {
  text: string
  highlighted: boolean
}

export interface TailoredExperience {
  company: string
  title: string
  location: string
  start_date: string
  end_date?: string
  bullets: TailoredBullet[]
}

export interface TailoredProject {
  name: string
  description: string
  tech_stack: string[]
  url?: string
  bullets: TailoredBullet[]
}

export interface CustomSection {
  title: string
  bullets: string[]
}

export interface TailoredResumeDraft {
  summary: string
  experiences: TailoredExperience[]
  education: Education[]
  projects: TailoredProject[]
  skills: Skill[]
  contact_info?: ContactInfo
  show_summary: boolean
  show_experiences: boolean
  show_education: boolean
  show_projects: boolean
  show_skills: boolean
  custom_sections: CustomSection[]
  template_id?: string | null
  template_source?: 'global' | 'user' | null
}

// ── auth ───────────────────────────────────────────────────────

export function registerUser(data: UserCreate): Promise<UserRead> {
  return request('/auth/register', { method: 'POST', body: JSON.stringify(data) })
}

export function updateUserMe(token: string, data: { full_name?: string }): Promise<UserRead> {
  return request('/users/me', { method: 'PUT', body: JSON.stringify(data) }, token)
}

export function loginUser(email: string, password: string): Promise<{ access_token: string; token_type: string }> {
  const body = new URLSearchParams({ username: email, password })
  return fetch(BASE + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  }).then(async r => {
    const data = await r.json()
    if (!r.ok) throw new ApiError(r.status, data.detail ?? JSON.stringify(data))
    return data
  })
}

// ── profile ────────────────────────────────────────────────────

export function getProfile(token: string): Promise<MasterProfile> {
  return request('/profile/', {}, token)
}

export function updateProfile(token: string, data: ProfileUpdate): Promise<MasterProfile> {
  return request('/profile/', { method: 'PUT', body: JSON.stringify(data) }, token)
}

export function appendSkills(token: string, skills: Skill[]): Promise<MasterProfile> {
  return request('/profile/skills', { method: 'POST', body: JSON.stringify({ skills }) }, token)
}

export function replaceSkills(token: string, skills: Skill[]): Promise<MasterProfile> {
  return request('/profile/skills', { method: 'PUT', body: JSON.stringify({ skills }) }, token)
}

export async function uploadResumePDF(token: string, file: File): Promise<ParsedProfileDraft> {
  const formData = new FormData()
  formData.append('file', file)
  const r = await fetch(BASE + '/profile/upload-pdf', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new ApiError(r.status, err.detail ?? JSON.stringify(err))
  }
  return r.json() as Promise<ParsedProfileDraft>
}

export function confirmParsedDraft(token: string, draft: ParsedProfileDraft): Promise<MasterProfile> {
  return request('/profile/upload-pdf/confirm', { method: 'POST', body: JSON.stringify(draft) }, token)
}

export function injectMockProfile(token: string, raw: string): Promise<MasterProfile> {
  return request('/profile/inject-mock', { method: 'POST', body: raw }, token)
}

// ── resume pipeline ────────────────────────────────────────────

export function analyzeJD(token: string, jd_text: string): Promise<MatchingPreview> {
  return request('/resume/analyze', { method: 'POST', body: JSON.stringify({ jd_text }) }, token)
}

export async function compileLatex(token: string, latex_content: string): Promise<Blob> {
  const r = await fetch(BASE + '/resume/compile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ latex_content }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new ApiError(r.status, err.detail ?? JSON.stringify(err))
  }
  return r.blob()
}

// ── sessions ───────────────────────────────────────────────────

export type ResumeSessionStatus = 'analyzing' | 'analyzed' | 'generating' | 'draft_ready' | 'failed'

export interface ResumeSessionSummary {
  id: string
  job_title?: string
  company?: string
  match_score?: number
  status: ResumeSessionStatus
  created_at: string
  updated_at: string
}

export interface ResumeSessionDetail {
  id: string
  jd_text: string
  jd?: JobDescription
  job_title?: string
  company?: string
  match_score?: number
  matched_skills: string[]
  missing_skills: string[]
  highlighted_experience_indices: number[]
  highlighted_project_indices: number[]
  all_experiences: WorkExperience[]
  all_projects: Project[]
  relevance_notes: string
  qualification_details?: QualificationResult[]
  status: ResumeSessionStatus
  tailored_draft?: TailoredResumeDraft
  kw_detail?: KeywordMatchResult
  created_at: string
  updated_at: string
}

export function listSessions(token: string, limit = 20, offset = 0): Promise<ResumeSessionSummary[]> {
  return request(`/sessions?limit=${limit}&offset=${offset}`, {}, token)
}

export function getSession(token: string, sessionId: string): Promise<ResumeSessionDetail> {
  return request(`/sessions/${sessionId}`, {}, token)
}

export function updateSessionDraft(token: string, sessionId: string, draft: TailoredResumeDraft): Promise<ResumeSessionSummary> {
  return request(`/sessions/${sessionId}/draft`, { method: 'PATCH', body: JSON.stringify({ tailored_draft: draft }) }, token)
}

export function deleteSession(token: string, sessionId: string): Promise<void> {
  return request(`/sessions/${sessionId}`, { method: 'DELETE' }, token)
}

// ── templates ──────────────────────────────────────────────────

export interface TemplateRead {
  id: string
  name: string
  industry?: string
  style_tag?: string
  description?: string
  preamble: string
  created_at: string
  source: 'global' | 'user'
}

export interface TemplateCreate {
  name: string
  industry?: string
  style_tag?: string
  description?: string
  preamble: string
  body_example?: string
}

export async function renderDraft(
  token: string,
  draft: TailoredResumeDraft,
  compile: boolean,
  template_id?: string | null,
  template_source?: 'global' | 'user' | null,
): Promise<Blob> {
  const r = await fetch(BASE + '/resume/render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ draft, compile, template_id: template_id ?? null, template_source: template_source ?? null }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new ApiError(r.status, err.detail ?? JSON.stringify(err))
  }
  return r.blob()
}

export function listTemplates(token: string): Promise<TemplateRead[]> {
  return request('/templates', {}, token)
}

export function createUserTemplate(token: string, data: TemplateCreate): Promise<TemplateRead> {
  return request('/templates/mine', { method: 'POST', body: JSON.stringify(data) }, token)
}

export function deleteUserTemplate(token: string, id: string): Promise<void> {
  return request(`/templates/mine/${id}`, { method: 'DELETE' }, token)
}

export function confirmGenerate(
  token: string,
  session_id: string,
  config: PipelineConfig,
  template_id?: string,
  template_source?: 'global' | 'user',
  selected_experience_indices?: number[],
  selected_project_indices?: number[],
): Promise<TailoredResumeDraft> {
  return request(
    '/resume/confirm',
    {
      method: 'POST',
      body: JSON.stringify({
        session_id,
        config,
        template_id: template_id ?? null,
        template_source: template_source ?? null,
        selected_experience_indices: selected_experience_indices ?? null,
        selected_project_indices: selected_project_indices ?? null,
      }),
    },
    token,
  )
}

export function tailorOneItem(
  token: string,
  session_id: string,
  item_type: 'exp' | 'proj',
  item_index: number,
): Promise<TailoredResumeDraft> {
  return request(
    '/resume/tailor-one',
    {
      method: 'POST',
      body: JSON.stringify({ session_id, item_type, item_index }),
    },
    token,
  )
}

export function tailorFull(
  token: string,
  session_id: string,
  template_id?: string,
  template_source?: 'global' | 'user',
  selected_experience_indices?: number[],
  selected_project_indices?: number[],
): Promise<TailoredResumeDraft> {
  return request(
    '/resume/tailor-full',
    {
      method: 'POST',
      body: JSON.stringify({
        session_id,
        template_id: template_id ?? null,
        template_source: template_source ?? null,
        selected_experience_indices: selected_experience_indices ?? null,
        selected_project_indices: selected_project_indices ?? null,
      }),
    },
    token,
  )
}

// ── css renderer ──────────────────────────────────────────────

export interface LayoutSettings {
  font_family: string
  font_size: number        // 1-5
  section_gap: number      // 1-5
  item_gap: number         // 1-5
  line_height: number      // 1-5
  margin_h: number         // mm 8-25
  margin_v: number         // mm 8-25
  compact_mode: boolean
  accent_color: string
}

export function defaultLayoutSettings(): LayoutSettings {
  return {
    font_family: 'Georgia',
    font_size: 3,
    section_gap: 3,
    item_gap: 3,
    line_height: 3,
    margin_h: 15,
    margin_v: 15,
    compact_mode: false,
    accent_color: '#1a1a1a',
  }
}

export async function previewHtml(
  token: string,
  draft: TailoredResumeDraft,
  settings: LayoutSettings,
  full_name: string,
): Promise<string> {
  const r = await fetch(BASE + '/resume/preview-html', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ draft, settings, full_name }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new ApiError(r.status, err.detail ?? JSON.stringify(err))
  }
  return r.text()
}

export async function exportPdf(
  token: string,
  draft: TailoredResumeDraft,
  settings: LayoutSettings,
  full_name: string,
): Promise<Blob> {
  const r = await fetch(BASE + '/resume/export-pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ draft, settings, full_name }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new ApiError(r.status, err.detail ?? JSON.stringify(err))
  }
  return r.blob()
}

// ── copilot types ─────────────────────────────────────────────

export type DiagnosticTier = 'tier1' | 'tier2' | 'tier3'

export interface DiagnosticTask {
  id: string
  tier: DiagnosticTier
  title: string
  description: string
  section?: string | null
  bullet_index?: number | null
  action_label?: string | null
  replaceable: boolean
  original_text?: string | null
  suggested_text?: string | null
  verify_condition?: string | null
}

export interface DiagnosticReport {
  tasks: DiagnosticTask[]
  req_score: number
  kw_score: number
  kw_detail?: KeywordMatchResult
}

export interface JobDescription {
  title: string
  company?: string
  qualifications: string[]
  tech_required: string[]
  tech_preferred: string[]
  nice_to_have: string[]
  tech_keywords?: string[]
  preferred_qualifications?: string[]
}

export interface MicroValidateRequest {
  text: string
  condition: string
}

export interface MicroValidateResponse {
  passed: boolean
  reasoning: string
}

export function diagnose(
  token: string,
  draft: TailoredResumeDraft,
  jd: JobDescription,
  profile: MasterProfile,
): Promise<DiagnosticReport> {
  return request('/copilot/diagnose', {
    method: 'POST',
    body: JSON.stringify({ draft, jd, profile }),
  }, token)
}

export function microValidate(
  token: string,
  text: string,
  condition: string,
): Promise<MicroValidateResponse> {
  return request('/copilot/micro-validate', {
    method: 'POST',
    body: JSON.stringify({ text, condition }),
  }, token)
}

export interface BatchVerifyResult {
  id: string
  reason: string
}

export interface BatchVerifyResponse {
  resolved: BatchVerifyResult[]
}

export function batchVerify(
  token: string,
  changed_sections: Record<string, string>,
  tasks: DiagnosticTask[],
): Promise<BatchVerifyResponse> {
  return request('/copilot/batch-verify', {
    method: 'POST',
    body: JSON.stringify({ changed_sections, tasks }),
  }, token)
}

// ── chat types ────────────────────────────────────────────────

export interface ChatScope {
  path: string
  label: string
}

export interface ResumePatch {
  path: string
  updated_value: unknown
  previous_value?: unknown
  diff_summary: string
}

export interface ChatMessage {
  id?: string
  role: 'user' | 'assistant'
  content: string
  scope?: ChatScope
  patch?: ResumePatch
  created_at?: string
}

export interface ResumeChatRequest {
  session_id: string
  draft: TailoredResumeDraft
  message: string
  scope?: ChatScope
  history: ChatMessage[]
}

export interface ResumeChatResponse {
  message: ChatMessage
  patch?: ResumePatch
}

// ── chat API ──────────────────────────────────────────────────

export function sendChatMessage(
  payload: ResumeChatRequest,
  token: string,
): Promise<ResumeChatResponse> {
  return request('/resume/chat', { method: 'POST', body: JSON.stringify(payload) }, token)
}

export function getChatHistory(sessionId: string, token: string): Promise<ChatMessage[]> {
  return request(`/resume/chat/${sessionId}`, {}, token)
}

export function undoLastPatch(sessionId: string, token: string): Promise<TailoredResumeDraft> {
  return request(`/resume/chat/${sessionId}/undo`, { method: 'POST' }, token)
}

export type StreamEvent =
  | { type: 'intent'; value: string }
  | { type: 'token'; content: string }
  | { type: 'patch'; path: string; updated_value: unknown; previous_value?: unknown; diff_summary: string }
  | { type: 'done'; reply: string }

export interface ProfileChatRequest {
  section_type: string
  section_index?: number
  section_data: unknown
  scope?: ChatScope
  message: string
  history: ChatMessage[]
}

export async function* streamProfileChatMessage(
  payload: ProfileChatRequest,
  token: string,
): AsyncGenerator<StreamEvent> {
  const resp = await fetch(BASE + '/profile/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    const detail = Array.isArray(err.detail)
      ? err.detail.map((e: { loc: string[]; msg: string }) => `${e.loc.join('.')}: ${e.msg}`).join('; ')
      : (err.detail ?? JSON.stringify(err))
    throw new ApiError(resp.status, detail)
  }

  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const line = part.trim()
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6)) as StreamEvent
        } catch {
          // malformed event, skip
        }
      }
    }
  }
}

export async function* streamChatMessage(
  payload: ResumeChatRequest,
  token: string,
): AsyncGenerator<StreamEvent> {
  const resp = await fetch(BASE + '/resume/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    const detail = Array.isArray(err.detail)
      ? err.detail.map((e: { loc: string[]; msg: string }) => `${e.loc.join('.')}: ${e.msg}`).join('; ')
      : (err.detail ?? JSON.stringify(err))
    throw new ApiError(resp.status, detail)
  }

  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const line = part.trim()
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6)) as StreamEvent
        } catch {
          // malformed event, skip
        }
      }
    }
  }
}
