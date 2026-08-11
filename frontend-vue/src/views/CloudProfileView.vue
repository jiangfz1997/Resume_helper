<template>
  <main class="profile-page">
    <header class="hero">
      <div>
        <span class="eyebrow">CANDIDATE PROFILE</span>
        <h1>Your resume source of truth.</h1>
        <p>Import one JSON file, review what was stored, and reuse it for future resume runs.</p>
      </div>
      <n-space>
        <n-button :disabled="!profile" @click="downloadProfile">Download JSON</n-button>
        <n-button :loading="loading" @click="loadProfile">Refresh</n-button>
      </n-space>
    </header>

    <n-alert v-if="loadError" type="error" class="page-alert">{{ loadError }}</n-alert>
    <div v-if="loading" class="loading"><n-spin size="large" /></div>

    <template v-else>
      <section class="summary-grid">
        <n-card size="small" class="identity-card">
          <template v-if="profile">
            <div class="identity-heading">
              <div>
                <span class="eyebrow">PROFILE V{{ profile.profile_version ?? 1 }}</span>
                <h2>{{ profile.full_name }}</h2>
              </div>
              <n-tag type="success" size="small">JSON schema v{{ profile.schema_version ?? 1 }}</n-tag>
            </div>
            <p v-if="profile.summary" class="profile-summary">{{ profile.summary }}</p>
            <p v-else class="muted">No summary in the current profile.</p>
            <div class="meta-row">
              <span>{{ profile.contact_info?.location || 'No location' }}</span>
              <span>Updated {{ formatDate(profile.updated_at) }}</span>
            </div>
          </template>
          <n-empty v-else description="No profile imported yet" />
        </n-card>

        <div class="stats">
          <div><b>{{ profile?.work_experiences.length ?? 0 }}</b><span>Work experiences</span></div>
          <div><b>{{ profile?.projects.length ?? 0 }}</b><span>Projects</span></div>
          <div><b>{{ profile?.educations.length ?? 0 }}</b><span>Education entries</span></div>
          <div><b>{{ profile?.skills.length ?? 0 }}</b><span>Skills</span></div>
        </div>
      </section>

      <section class="content-grid">
        <n-card title="Import profile JSON" size="small" class="import-card">
          <p class="hint">
            A valid import replaces the complete profile. Download the current JSON first if you want a backup.
          </p>
          <n-upload
            accept=".json,application/json"
            :max="1"
            :default-upload="false"
            :show-file-list="false"
            @change="onFileChange"
          >
            <n-upload-dragger>
              <div class="drop-zone">
                <strong>Drop a JSON file here</strong>
                <span>or click to choose one</span>
              </div>
            </n-upload-dragger>
          </n-upload>

          <n-divider>or paste JSON</n-divider>
          <n-input
            v-model:value="jsonText"
            type="textarea"
            :autosize="{ minRows: 12, maxRows: 24 }"
            placeholder="Paste your candidate profile JSON here..."
            class="json-input"
          />

          <n-alert v-if="importError" type="error" class="import-alert">{{ importError }}</n-alert>
          <n-alert v-else-if="preview" type="success" class="import-alert">
            Valid profile for {{ preview.full_name }}: {{ preview.work_experiences?.length ?? 0 }} work experiences,
            {{ preview.projects?.length ?? 0 }} projects, and {{ preview.skills?.length ?? 0 }} skills.
          </n-alert>

          <footer class="import-actions">
            <n-button @click="loadExample">Load example</n-button>
            <n-button :disabled="!jsonText.trim()" @click="validateImport">Validate</n-button>
            <n-popconfirm
              :disabled="!preview || saving"
              positive-text="Replace profile"
              negative-text="Cancel"
              @positive-click="saveImport"
            >
              <template #trigger>
                <n-button type="primary" :loading="saving" :disabled="!preview">Import and replace</n-button>
              </template>
              This replaces the complete profile currently stored for your account.
            </n-popconfirm>
          </footer>
        </n-card>

        <div class="library">
          <n-card title="Work experience" size="small">
            <n-empty v-if="!profile?.work_experiences.length" description="No work experience" size="small" />
            <div v-for="experience in profile?.work_experiences" :key="experience.id || `${experience.company}-${experience.title}`" class="library-item">
              <strong>{{ experience.title || 'Untitled role' }}</strong>
              <span>{{ experience.company || 'Unknown company' }} · {{ dateRange(experience.start_date, experience.end_date) }}</span>
              <ul v-if="experience.bullets?.length">
                <li v-for="bullet in experience.bullets" :key="bullet">{{ bullet }}</li>
              </ul>
            </div>
          </n-card>

          <n-card title="Projects" size="small">
            <n-empty v-if="!profile?.projects.length" description="No projects" size="small" />
            <div v-for="project in profile?.projects" :key="project.id || project.name" class="library-item">
              <strong>{{ project.name || 'Untitled project' }}</strong>
              <span>{{ project.tech_stack?.join(', ') || project.description || 'No description' }}</span>
              <ul v-if="project.bullets?.length">
                <li v-for="bullet in project.bullets" :key="bullet">{{ bullet }}</li>
              </ul>
            </div>
          </n-card>

          <n-card title="Education" size="small">
            <n-empty v-if="!profile?.educations.length" description="No education" size="small" />
            <div
              v-for="education in profile?.educations"
              :key="`${education.institution}-${education.degree}-${education.end_date}`"
              class="library-item"
            >
              <strong>{{ education.degree || 'Untitled degree' }}<template v-if="education.field_of_study"> · {{ education.field_of_study }}</template></strong>
              <span>{{ education.institution || 'Unknown institution' }} · {{ dateRange(education.start_date, education.end_date) }}</span>
            </div>
          </n-card>

          <n-card title="Skills" size="small">
            <n-empty v-if="!profile?.skills.length" description="No skills" size="small" />
            <div v-for="(skills, category) in groupedSkills" :key="category" class="skill-group">
              <strong>{{ category }}</strong>
              <n-space size="small">
                <n-tag v-for="skill in skills" :key="skill.name" size="small">{{ skill.name }}</n-tag>
              </n-space>
            </div>
          </n-card>
        </div>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import type { UploadFileInfo } from 'naive-ui'
import { useMessage } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { profileDataSource } from '../profile/dataSource'
import type { CandidateProfile, CandidateProfileInput, Skill } from '../profile/models'

const message = useMessage()
const profile = ref<CandidateProfile | null>(null)
const loading = ref(true)
const saving = ref(false)
const loadError = ref('')
const importError = ref('')
const jsonText = ref('')
const preview = ref<CandidateProfileInput | null>(null)

const groupedSkills = computed<Record<string, Skill[]>>(() => {
  const groups: Record<string, Skill[]> = {}
  for (const skill of profile.value?.skills ?? []) {
    ;(groups[skill.category] ??= []).push(skill)
  }
  return groups
})

onMounted(loadProfile)

async function loadProfile(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    profile.value = await profileDataSource.getProfile()
  } catch (reason) {
    loadError.value = reason instanceof Error ? reason.message : 'Unable to load profile.'
  } finally {
    loading.value = false
  }
}

async function onFileChange({ file }: { file: UploadFileInfo }): Promise<void> {
  if (!file.file) return
  if (file.file.size > 1_000_000) {
    preview.value = null
    importError.value = 'Profile JSON must be smaller than 1 MB.'
    return
  }
  jsonText.value = await file.file.text()
  validateImport()
}

function validateImport(): void {
  try {
    preview.value = parseProfileJson(jsonText.value)
    importError.value = ''
  } catch (reason) {
    preview.value = null
    importError.value = reason instanceof Error ? reason.message : 'Invalid profile JSON.'
  }
}

async function saveImport(): Promise<void> {
  if (!preview.value) return
  saving.value = true
  try {
    profile.value = await profileDataSource.saveProfile(preview.value)
    message.success(`Profile v${profile.value.profile_version ?? 1} imported.`)
    preview.value = null
    jsonText.value = ''
  } catch (reason) {
    importError.value = reason instanceof Error ? reason.message : 'Unable to import profile.'
  } finally {
    saving.value = false
  }
}

function downloadProfile(): void {
  if (!profile.value) return
  const exported: CandidateProfileInput = {
    schema_version: 1,
    full_name: profile.value.full_name,
    summary: profile.value.summary ?? null,
    contact_info: profile.value.contact_info ?? null,
    work_experiences: profile.value.work_experiences,
    educations: profile.value.educations,
    projects: profile.value.projects,
    skills: profile.value.skills,
  }
  const blob = new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'candidate-profile.json'
  link.click()
  URL.revokeObjectURL(url)
}

function loadExample(): void {
  jsonText.value = JSON.stringify(EXAMPLE_PROFILE, null, 2)
  validateImport()
}

function parseProfileJson(raw: string): CandidateProfileInput {
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch (reason) {
    throw new Error(`Invalid JSON syntax: ${reason instanceof Error ? reason.message : 'parse failed'}`)
  }
  const root = requireObject(value, 'profile')
  if (root.schema_version !== undefined && root.schema_version !== 1) {
    throw new Error('schema_version must be 1.')
  }
  const fullName = requireString(root.full_name, 'full_name')
  validateOptionalString(root.summary, 'summary')
  validateContact(root.contact_info)
  validateObjectList(root.work_experiences, 'work_experiences', ['id', 'company', 'title', 'location', 'start_date', 'end_date'], ['bullets'])
  validateObjectList(root.educations, 'educations', ['institution', 'degree', 'field_of_study', 'start_date', 'end_date', 'gpa'], [])
  validateObjectList(root.projects, 'projects', ['id', 'name', 'description', 'url'], ['bullets', 'tech_stack'])
  validateSkills(root.skills)
  return {
    schema_version: 1,
    full_name: fullName,
    summary: root.summary as string | null | undefined,
    contact_info: root.contact_info as CandidateProfileInput['contact_info'],
    work_experiences: (root.work_experiences ?? []) as CandidateProfileInput['work_experiences'],
    educations: (root.educations ?? []) as CandidateProfileInput['educations'],
    projects: (root.projects ?? []) as CandidateProfileInput['projects'],
    skills: (root.skills ?? []) as Skill[],
  }
}

function requireObject(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${path} must be a JSON object.`)
  return value as Record<string, unknown>
}

function requireString(value: unknown, path: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${path} must be a non-empty string.`)
  return value
}

function validateOptionalString(value: unknown, path: string): void {
  if (value !== undefined && value !== null && typeof value !== 'string') throw new Error(`${path} must be a string or null.`)
}

function validateContact(value: unknown): void {
  if (value === undefined || value === null) return
  const contact = requireObject(value, 'contact_info')
  for (const field of ['email', 'phone', 'location', 'linkedin', 'github', 'website']) {
    validateOptionalString(contact[field], `contact_info.${field}`)
  }
}

function validateObjectList(
  value: unknown,
  path: string,
  stringFields: string[],
  stringArrayFields: string[],
): void {
  if (value === undefined) return
  if (!Array.isArray(value)) throw new Error(`${path} must be an array.`)
  value.forEach((entry, index) => {
    const item = requireObject(entry, `${path}[${index}]`)
    for (const field of stringFields) validateOptionalString(item[field], `${path}[${index}].${field}`)
    for (const field of stringArrayFields) validateStringArray(item[field], `${path}[${index}].${field}`)
  })
}

function validateStringArray(value: unknown, path: string): void {
  if (value === undefined) return
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new Error(`${path} must be an array of strings.`)
  }
}

function validateSkills(value: unknown): void {
  if (value === undefined) return
  if (!Array.isArray(value)) throw new Error('skills must be an array.')
  value.forEach((entry, index) => {
    const skill = requireObject(entry, `skills[${index}]`)
    requireString(skill.category, `skills[${index}].category`)
    requireString(skill.name, `skills[${index}].name`)
    const proficiency = skill.proficiency
    if (proficiency !== undefined && proficiency !== null && !['expert', 'intermediate', 'beginner'].includes(String(proficiency))) {
      throw new Error(`skills[${index}].proficiency must be expert, intermediate, beginner, or null.`)
    }
  })
}

function dateRange(start?: string, end?: string | null): string {
  return `${start || 'Unknown'} – ${end || 'Present'}`
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

const EXAMPLE_PROFILE: CandidateProfileInput = {
  schema_version: 1,
  full_name: 'Your Name',
  summary: 'Software engineer focused on backend and AI systems.',
  contact_info: { email: 'you@example.com', location: 'Toronto, ON', github: 'https://github.com/you' },
  work_experiences: [{
    company: 'Company A', title: 'Software Engineer', location: 'Toronto, ON',
    start_date: '2024-01', end_date: null, bullets: ['Built a production service.', 'Improved system reliability.'],
  }],
  educations: [{
    institution: 'Western University', degree: 'Master of Engineering', field_of_study: 'Software Engineering',
    start_date: '2025-09', end_date: '2026-12', gpa: null,
  }],
  projects: [{
    name: 'Job Discovery Platform', description: 'Serverless job discovery and resume tailoring platform.',
    bullets: ['Designed the serverless architecture.'], tech_stack: ['Python', 'AWS Lambda', 'DynamoDB', 'Vue'], url: null,
  }],
  skills: [{ category: 'Languages', name: 'Python', proficiency: 'expert' }],
}
</script>

<style scoped>
.profile-page { min-height: calc(100vh - 56px); padding: 30px 34px 56px; color: #edf1f7; background: radial-gradient(circle at 8% -15%, rgba(58,121,255,.15), transparent 32%), #0b0d12; }
.hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; max-width: 1440px; margin: 0 auto 24px; }
.eyebrow { color: #9ac4ff; font: 750 11px/1.35 system-ui, sans-serif; letter-spacing: .105em; }
.hero h1 { margin: 8px 0 6px; font-size: clamp(27px, 3vw, 40px); letter-spacing: -.035em; }
.hero p, .hint, .muted { margin: 0; color: #8e98a9; }
.page-alert, .summary-grid, .content-grid, .loading { max-width: 1440px; margin: 0 auto 20px; }
.loading { display: grid; min-height: 300px; place-items: center; }
.summary-grid { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(320px, 1fr); gap: 16px; }
.identity-heading { display: flex; justify-content: space-between; gap: 20px; }
.identity-heading h2 { margin: 5px 0 0; font-size: 24px; }
.profile-summary { margin: 16px 0; color: #c7ced9; line-height: 1.65; }
.meta-row { display: flex; justify-content: space-between; gap: 12px; margin-top: 16px; color: #778194; font-size: 12px; }
.stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.stats div { display: flex; flex-direction: column; justify-content: center; min-height: 92px; padding: 15px; border: 1px solid rgba(255,255,255,.08); border-radius: 8px; background: #12151c; }
.stats b { font-size: 25px; color: #9ac4ff; }
.stats span { margin-top: 4px; color: #8e98a9; font-size: 11px; text-transform: uppercase; }
.content-grid { display: grid; grid-template-columns: minmax(420px, .9fr) minmax(0, 1.25fr); gap: 16px; align-items: start; }
.hint { margin-bottom: 15px; font-size: 12px; line-height: 1.5; }
.drop-zone { display: flex; flex-direction: column; gap: 5px; padding: 22px; }
.drop-zone span { color: #8e98a9; font-size: 12px; }
.json-input { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }
.import-alert { margin-top: 14px; }
.import-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 16px; }
.library { display: grid; gap: 16px; }
.library-item { padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,.07); }
.library-item:last-child { border-bottom: 0; }
.library-item > strong, .library-item > span { display: block; }
.library-item > span { margin-top: 3px; color: #8e98a9; font-size: 12px; }
.library-item ul { margin: 9px 0 0; padding-left: 19px; color: #bcc4d0; font-size: 12px; line-height: 1.55; }
.skill-group { display: grid; grid-template-columns: 130px 1fr; gap: 12px; align-items: start; padding: 7px 0; }
.skill-group strong { color: #aeb8c7; font-size: 12px; }
@media (max-width: 900px) { .summary-grid, .content-grid { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .profile-page { padding: 24px 16px 40px; } .hero { align-items: flex-start; flex-direction: column; } .stats { grid-template-columns: 1fr 1fr; } .import-actions { flex-wrap: wrap; } }
</style>
