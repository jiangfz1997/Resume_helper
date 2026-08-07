<template>
  <div class="applications-page">
    <n-page-header title="Applications" subtitle="Every role you've applied to, from either entry point" />

    <section class="stats-row">
      <div class="stat-tile">
        <span class="stat-label">Today</span>
        <span class="stat-value">{{ stats.today }}</span>
      </div>
      <div class="stat-tile">
        <span class="stat-label">This week</span>
        <span class="stat-value">{{ stats.thisWeek }}</span>
      </div>
      <div class="stat-tile">
        <span class="stat-label">Total</span>
        <span class="stat-value">{{ stats.total }}</span>
      </div>
      <div class="stat-tile status-breakdown">
        <span class="stat-label">By status</span>
        <div class="status-chips">
          <n-tag v-for="entry in statusBreakdown" :key="entry.status" :type="statusTagType(entry.status)" size="small" round>
            {{ statusLabel(entry.status) }} · {{ entry.count }}
          </n-tag>
          <span v-if="!statusBreakdown.length" class="muted">Nothing tracked yet</span>
        </div>
      </div>
    </section>

    <section class="toolbar">
      <n-select v-model:value="statusFilter" :options="statusFilterOptions" style="width: 220px" />
      <n-button type="primary" @click="showAddDialog = true">+ Add application</n-button>
    </section>

    <n-alert v-if="loadError" type="error" style="margin-bottom: 16px">{{ loadError }}</n-alert>

    <n-data-table
      v-if="!loading"
      :columns="columns"
      :data="visibleApplications"
      :row-key="(row: JobApplication) => row.applicationId"
      :pagination="{ pageSize: 20 }"
    />
    <div v-else class="loading"><n-spin size="large" /></div>

    <n-empty v-if="!loading && !visibleApplications.length" description="No applications match this filter" style="margin-top: 24px" />

    <n-modal v-model:show="showAddDialog" preset="card" title="Add application from a link" style="max-width: 480px">
      <n-form :model="addForm">
        <n-form-item label="Job posting URL" required>
          <n-input v-model:value="addForm.url" placeholder="https://..." @keydown.enter="submitAdd" />
        </n-form-item>
      </n-form>
      <p class="hint">We'll fetch the page, save a copy of the posting, and pull out the company/title automatically.</p>
      <template #footer>
        <n-button type="primary" block :loading="addLoading" :disabled="!addForm.url.trim()" @click="submitAdd">
          Save application
        </n-button>
      </template>
    </n-modal>

    <n-drawer v-model:show="showDetail" :width="520">
      <n-drawer-content v-if="selected" :title="`${selected.company} — ${selected.title}`" closable>
        <n-space vertical size="large">
          <n-space align="center">
            <n-tag :type="statusTagType(selected.status)">{{ statusLabel(selected.status) }}</n-tag>
            <n-tag v-if="selected.extractionStatus === 'extracting'" type="warning">Extracting…</n-tag>
            <n-tag v-else-if="selected.extractionStatus === 'failed'" type="error">Extraction failed</n-tag>
          </n-space>

          <n-form-item label="Update status">
            <n-select
              :value="selected.status"
              :options="statusOptions"
              @update:value="(value: ApplicationStatus) => updateStatus(selected!.applicationId, value)"
            />
          </n-form-item>

          <div v-if="selected.location"><b>Location:</b> {{ selected.location }}</div>
          <div><b>Applied:</b> {{ formatDate(selected.appliedAt) }}</div>
          <a v-if="selected.sourceUrl" :href="selected.sourceUrl" target="_blank" rel="noopener noreferrer">Open original posting ↗</a>

          <div>
            <span class="eyebrow">JOB DESCRIPTION</span>
            <pre class="jd-text">{{ selected.jdText || (selected.extractionStatus === 'extracting' ? 'Extracting…' : 'No description captured.') }}</pre>
          </div>

          <div>
            <span class="eyebrow">STATUS HISTORY</span>
            <ul class="history">
              <li v-for="(event, index) in [...selected.statusHistory].reverse()" :key="index">
                <b>{{ statusLabel(event.status) }}</b> — {{ formatDate(event.changedAt) }}
                <span v-if="event.note"> · {{ event.note }}</span>
              </li>
            </ul>
          </div>

          <n-button type="error" quaternary @click="removeApplication(selected.applicationId)">Delete this record</n-button>
        </n-space>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { NTag, useMessage, type DataTableColumns } from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { applicationDataSource } from '../applications/dataSource'
import type { ApplicationStats, ApplicationStatus, JobApplication } from '../applications/models'

const message = useMessage()

const applications = ref<JobApplication[]>([])
const stats = ref<ApplicationStats>({ today: 0, thisWeek: 0, total: 0, byStatus: {} })
const loading = ref(true)
const loadError = ref('')
const statusFilter = ref<'all' | ApplicationStatus>('all')
const showAddDialog = ref(false)
const addLoading = ref(false)
const addForm = ref({ url: '' })
const showDetail = ref(false)
const selectedId = ref<string | null>(null)

const selected = computed(() => applications.value.find((application) => application.applicationId === selectedId.value) ?? null)
const visibleApplications = computed(() => statusFilter.value === 'all'
  ? applications.value
  : applications.value.filter((application) => application.status === statusFilter.value))
const statusBreakdown = computed(() => Object.entries(stats.value.byStatus)
  .map(([status, count]) => ({ status: status as ApplicationStatus, count: count ?? 0 }))
  .filter((entry) => entry.count > 0))

const statusOptions: { label: string; value: ApplicationStatus }[] = [
  { label: 'Applied', value: 'applied' },
  { label: 'Resume rejected', value: 'resume_rejected' },
  { label: 'Interviewing', value: 'interviewing' },
  { label: 'Interview rejected', value: 'interview_rejected' },
  { label: 'Offer', value: 'offer' },
  { label: 'Accepted', value: 'accepted' },
  { label: 'Withdrawn', value: 'withdrawn' },
]
const statusFilterOptions = [{ label: 'All statuses', value: 'all' }, ...statusOptions]

const columns: DataTableColumns<JobApplication> = [
  { title: 'Company', key: 'company' },
  { title: 'Title', key: 'title' },
  {
    title: 'Status',
    key: 'status',
    render: (row) => h(NTag, { type: statusTagType(row.status), size: 'small' }, { default: () => statusLabel(row.status) }),
  },
  { title: 'Source', key: 'sourceType', render: (row) => (row.sourceType === 'dashboard' ? 'Dashboard' : 'Manual link') },
  { title: 'Applied', key: 'appliedAt', render: (row) => formatDate(row.appliedAt) },
  {
    title: '',
    key: 'actions',
    render: (row) => h('a', { class: 'row-link', onClick: () => openDetail(row.applicationId) }, 'View'),
  },
]

onMounted(load)

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const [loadedApplications, loadedStats] = await Promise.all([
      applicationDataSource.listApplications(),
      applicationDataSource.getStats(),
    ])
    applications.value = loadedApplications
    stats.value = loadedStats
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : 'Unable to load applications.'
  } finally {
    loading.value = false
  }
}

function openDetail(applicationId: string): void {
  selectedId.value = applicationId
  showDetail.value = true
}

async function submitAdd(): Promise<void> {
  const url = addForm.value.url.trim()
  if (!url) return
  addLoading.value = true
  try {
    const created = await applicationDataSource.createFromUrl(url)
    applications.value = [created, ...applications.value]
    stats.value = await applicationDataSource.getStats()
    addForm.value.url = ''
    showAddDialog.value = false
    message.success('Saved. Extracting job details in the background…')
    if (created.extractionStatus === 'extracting') pollExtraction(created.applicationId)
  } catch (error) {
    message.error(error instanceof Error ? error.message : 'Could not save this application.')
  } finally {
    addLoading.value = false
  }
}

function pollExtraction(applicationId: string, attempt = 0): void {
  if (attempt >= 6) return
  setTimeout(async () => {
    const refreshed = await applicationDataSource.refreshApplication(applicationId)
    if (!refreshed) return
    applications.value = applications.value.map((application) => application.applicationId === applicationId ? refreshed : application)
    if (refreshed.extractionStatus === 'extracting') pollExtraction(applicationId, attempt + 1)
  }, 3000)
}

async function updateStatus(applicationId: string, status: ApplicationStatus): Promise<void> {
  const updated = await applicationDataSource.updateStatus(applicationId, status)
  applications.value = applications.value.map((application) => application.applicationId === applicationId ? updated : application)
  stats.value = await applicationDataSource.getStats()
}

async function removeApplication(applicationId: string): Promise<void> {
  await applicationDataSource.deleteApplication(applicationId)
  applications.value = applications.value.filter((application) => application.applicationId !== applicationId)
  showDetail.value = false
  stats.value = await applicationDataSource.getStats()
}

function statusLabel(status: ApplicationStatus): string {
  return statusOptions.find((option) => option.value === status)?.label ?? status
}
function statusTagType(status: ApplicationStatus): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (status === 'offer' || status === 'accepted') return 'success'
  if (status === 'interviewing') return 'info'
  if (status === 'resume_rejected' || status === 'interview_rejected') return 'error'
  if (status === 'applied') return 'warning'
  return 'default'
}
function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en-CA', { month: 'short', day: 'numeric', year: 'numeric' }).format(Date.parse(value))
}
</script>

<style scoped>
.applications-page { padding: 8px 4px 40px; }
.stats-row { display: grid; grid-template-columns: repeat(3, 140px) 1fr; gap: 12px; margin: 20px 0; }
.stat-tile { display: flex; flex-direction: column; gap: 4px; padding: 14px 16px; border: 1px solid #2e2e2e; border-radius: 8px; }
.stat-label { font-size: 11px; letter-spacing: .05em; color: #888; text-transform: uppercase; }
.stat-value { font-size: 26px; font-weight: 700; }
.status-breakdown .status-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.muted { color: #666; font-size: 12px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.loading { display: grid; place-items: center; height: 240px; }
.hint { color: #888; font-size: 12px; margin-top: 4px; }
.eyebrow { display: block; margin-bottom: 6px; color: #6fa8ff; font: 700 10px/1.3 monospace; letter-spacing: .12em; }
.jd-text { max-height: 320px; overflow-y: auto; padding: 12px; border: 1px solid #2e2e2e; border-radius: 8px; white-space: pre-wrap; font-size: 12px; line-height: 1.6; }
.history { margin: 0; padding-left: 18px; font-size: 12px; color: #ccc; }
.history li { margin-bottom: 4px; }
:deep(.row-link) { color: #6fa8ff; cursor: pointer; }
</style>
