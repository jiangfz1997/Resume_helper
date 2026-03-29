<template>
  <div>
    <n-page-header title="Resume Sessions" style="margin-bottom: 20px" />

    <n-spin v-if="loading" />

    <n-empty v-else-if="sessions.length === 0" description="No sessions yet. Go to Generate to start." style="margin-top: 40px" />

    <n-space v-else vertical size="medium">
      <div
        v-for="s in sessions"
        :key="s.id"
        style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border:1px solid #2e2e2e;border-radius:8px"
      >
        <div style="display:flex;flex-direction:column;gap:6px;flex:1;min-width:0">
          <n-space align="center" size="small">
            <span style="font-size:14px;font-weight:600">
              {{ s.job_title ?? 'Untitled' }}
              <span v-if="s.company" style="font-weight:400;color:#888"> @ {{ s.company }}</span>
            </span>
            <n-tag :type="statusType(s.status)" size="tiny">{{ s.status }}</n-tag>
          </n-space>
          <n-space align="center" size="small">
            <span v-if="s.match_score != null" style="font-size:12px;color:#aaa">
              Match: {{ Math.round(s.match_score * 100) }}%
            </span>
            <span style="font-size:12px;color:#666">{{ formatDate(s.created_at) }}</span>
          </n-space>
        </div>

        <n-space size="small">
          <n-button
            v-if="s.status === 'analyzed' || s.status === 'draft_ready'"
            size="small"
            type="primary"
            @click="resumeSession(s)"
          >
            {{ s.status === 'draft_ready' ? 'View Draft' : 'Continue' }}
          </n-button>
          <!-- DEPRECATED: PDF download from session list disabled (format broken) -->
          <!-- <n-button
            v-if="s.status === 'draft_ready'"
            size="small"
            @click="renderPdf(s)"
            :loading="renderingId === s.id"
          >
            PDF
          </n-button> -->
          <n-button size="small" quaternary type="error" @click="confirmDelete(s)">Delete</n-button>
        </n-space>
      </div>

      <n-button v-if="hasMore" dashed @click="loadMore">Load more</n-button>
    </n-space>

    <n-alert v-if="error" type="error" style="margin-top: 16px">{{ error }}</n-alert>
  </div>
</template>

<script setup lang="ts">
import { useMessage } from 'naive-ui'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  deleteSession,
  getSession,
  listSessions,
  renderDraft,
  type ResumeSessionSummary,
  type ResumeSessionStatus,
} from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const message = useMessage()
const token = () => auth.token!

const sessions = ref<ResumeSessionSummary[]>([])
const loading = ref(false)
const error = ref('')
const offset = ref(0)
const hasMore = ref(false)
const LIMIT = 20
const renderingId = ref<string | null>(null)

function statusType(s: ResumeSessionStatus): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (s === 'draft_ready') return 'success'
  if (s === 'analyzing' || s === 'generating') return 'warning'
  if (s === 'failed') return 'error'
  if (s === 'analyzed') return 'info'
  return 'default'
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

async function fetchSessions(replace = true): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const data = await listSessions(token(), LIMIT, replace ? 0 : offset.value)
    if (replace) {
      sessions.value = data
      offset.value = data.length
    } else {
      sessions.value.push(...data)
      offset.value += data.length
    }
    hasMore.value = data.length === LIMIT
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

async function loadMore(): Promise<void> {
  await fetchSessions(false)
}

onMounted(() => fetchSessions())

async function resumeSession(s: ResumeSessionSummary): Promise<void> {
  router.push({ path: '/generate', query: { session_id: s.id } })
}

async function renderPdf(s: ResumeSessionSummary): Promise<void> {
  renderingId.value = s.id
  try {
    const detail = await getSession(token(), s.id)
    if (!detail.tailored_draft) { message.warning('No draft available'); return }
    const blob = await renderDraft(
      token(),
      detail.tailored_draft,
      true,
      detail.tailored_draft.template_id ?? null,
      detail.tailored_draft.template_source ?? null,
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `resume_${s.job_title ?? s.id}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    renderingId.value = null
  }
}

async function confirmDelete(s: ResumeSessionSummary): Promise<void> {
  if (!window.confirm(`Delete session "${s.job_title ?? s.id}"?`)) return
  try {
    await deleteSession(token(), s.id)
    sessions.value = sessions.value.filter(x => x.id !== s.id)
    message.success('Session deleted')
  } catch (e) {
    message.error((e as Error).message)
  }
}
</script>
