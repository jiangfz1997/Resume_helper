<template>
  <main class="jobs-page">
    <header class="hero">
      <div>
        <span class="eyebrow">JOB DISCOVERY / PERSONAL INBOX</span>
        <h1>Your next role, without the noise.</h1>
        <p>Review discovered roles, understand their coarse score, and build a focused shortlist.</p>
      </div>
      <div class="snapshot"><i /><div><b>{{ pendingCount }} pending · {{ unreadRunCount }} unread runs</b><small>{{ scoringQueue.scoredCurrent }} scored · {{ scoringQueue.pending }} waiting · {{ scoringQueue.queued }} queued · {{ scoringQueue.failed }} failed · {{ unviewedCount }} unopened</small></div></div>
    </header>

    <section class="filters">
      <n-input v-model:value="search" clearable placeholder="Search title, company, or location..." class="search" />
      <n-select v-model:value="category" :options="categoryOptions" />
      <n-select v-model:value="runFilter" :options="runOptions" />
      <n-select v-model:value="eligibility" :options="eligibilityOptions" />
      <n-select v-model:value="score" :options="scoreOptions" />
      <n-select v-model:value="freshness" :options="freshnessOptions" />
      <n-select v-model:value="sort" :options="sortOptions" />
    </section>

    <section v-if="selectedRunSummary" :class="['run-health', `is-${selectedRunSummary.status}`]">
      <b>{{ formatRun(selectedRunSummary) }}</b>
      <span>{{ selectedRunSummary.newJobsCount }} new · {{ selectedRunSummary.observedCount }} observed · {{ selectedRunSummary.eligibleCount }} eligible</span>
      <span>{{ selectedRunSummary.sources.map(sourceLabel).join(', ') || 'Legacy run' }}</span>
      <strong v-if="selectedRunSummary.errorCount">{{ selectedRunSummary.errorCount }} errors</strong>
    </section>

    <nav class="tabs">
      <button v-for="tab in statusTabs" :key="tab.value" :class="{ active: status === tab.value }" @click="status = tab.value">
        {{ tab.label }} <span>{{ tab.count }}</span>
      </button>
      <small>{{ visibleJobs.length }} results</small>
    </nav>

    <n-alert v-if="loadError" type="error" class="load-error">{{ loadError }}</n-alert>
    <section v-if="!loading && !loadError && visibleJobs.length" class="workspace">
      <div class="job-list">
        <article
          v-for="job in visibleJobs"
          :key="job.jobId"
          :class="['job-row', { selected: selectedJobId === job.jobId, rejected: statusFor(job.jobId) === 'rejected' }]"
          @click="selectJob(job.jobId)"
        >
          <div class="logo">{{ initials(job.company) }}</div>
          <div class="row-main">
            <div class="topline"><span>{{ job.company }}</span><small>{{ relativeDate(job.postedAt ?? job.firstSeenAt) }}</small></div>
            <h2>{{ job.title }}</h2>
            <p>{{ job.location }} · {{ workplaceLabel(job.workplaceType) }}<template v-if="job.sources[0]"> · {{ sourceLabel(job.sources[0]) }}</template></p>
            <div v-if="job.requiredYearsMin !== null || job.requirementKeywords.length" class="requirements">
              <span v-if="job.requiredYearsMin !== null" class="years">{{ yearsLabel(job.requiredYearsMin, job.requiredYearsMax) }}</span>
              <span v-for="keyword in job.requirementKeywords.slice(0, 4)" :key="keyword" class="keyword" :title="keyword">{{ keyword }}</span>
              <small v-if="job.requirementKeywords.length > 4">+{{ job.requirementKeywords.length - 4 }}</small>
            </div>
            <footer>
              <em v-if="job.jobCategory" class="is-category">{{ job.jobCategory.toUpperCase() }}</em>
              <em v-if="!isViewed(job.jobId)" class="is-new">new</em>
              <em :class="`is-${job.eligibilityStatus}`">{{ job.eligibilityStatus }}</em>
              <em v-if="job.lifecycleStatus !== 'active'" :class="`lifecycle-${job.lifecycleStatus}`">{{ job.lifecycleStatus }}</em>
              <em v-if="statusFor(job.jobId) !== 'new'" class="user-status">{{ statusLabel(statusFor(job.jobId)) }}</em>
            </footer>
          </div>
          <div class="side-col">
            <div class="quick-actions">
              <a
                v-if="job.primaryListingUrl"
                :href="job.primaryListingUrl"
                target="_blank"
                rel="noopener noreferrer"
                title="Open original listing"
                @click.stop
              >↗</a>
              <button
                :class="{ active: statusFor(job.jobId) === 'rejected' }"
                :title="statusFor(job.jobId) === 'rejected' ? 'Restore' : 'Not interested'"
                @click.stop="toggleStatus(job.jobId, 'rejected')"
              >{{ statusFor(job.jobId) === 'rejected' ? '↩' : '✕' }}</button>
            </div>
            <div :class="['score', scoreClass(scoreFor(job.jobId))]"><b>{{ scoreFor(job.jobId) ?? '—' }}</b><small>/ 10</small></div>
          </div>
        </article>
      </div>

      <aside v-if="selectedJob" class="detail">
        <header>
          <div><span>{{ selectedJob.company }}</span><h2>{{ selectedJob.title }}</h2><p>{{ selectedJob.location }} · {{ workplaceLabel(selectedJob.workplaceType) }}</p></div>
          <div :class="['detail-score', scoreClass(scoreFor(selectedJob.jobId))]"><b>{{ scoreFor(selectedJob.jobId) ?? '—' }}</b><small>your fit</small></div>
        </header>

        <div class="actions">
          <n-button :type="statusFor(selectedJob.jobId) === 'saved' ? 'primary' : 'default'" @click="toggleStatus(selectedJob.jobId, 'saved')">{{ statusFor(selectedJob.jobId) === 'saved' ? 'Saved' : 'Save role' }}</n-button>
          <n-button :type="statusFor(selectedJob.jobId) === 'selected' ? 'success' : 'default'" @click="toggleStatus(selectedJob.jobId, 'selected')">{{ statusFor(selectedJob.jobId) === 'selected' ? 'In shortlist' : 'Shortlist' }}</n-button>
          <n-button :type="statusFor(selectedJob.jobId) === 'applied' ? 'success' : 'default'" @click="toggleStatus(selectedJob.jobId, 'applied')">{{ statusFor(selectedJob.jobId) === 'applied' ? 'Applied' : 'Mark applied' }}</n-button>
          <n-button quaternary type="error" @click="toggleStatus(selectedJob.jobId, 'rejected')">{{ statusFor(selectedJob.jobId) === 'rejected' ? 'Restore' : 'Reject' }}</n-button>
          <n-button v-if="scoreFor(selectedJob.jobId) === null" :disabled="isScoreQueued(selectedJob.jobId)" @click="queueScore(selectedJob.jobId)">{{ isScoreQueued(selectedJob.jobId) ? 'Queued' : scoringAttemptFor(selectedJob.jobId)?.scoringStatus === 'failed' ? 'Retry score' : 'Score now' }}</n-button>
          <n-button type="primary" class="generate" @click="sendToGenerate(selectedJob)">Generate resume</n-button>
        </div>

        <section :class="['reasoning', { pending: !assessmentFor(selectedJob.jobId)?.coarseScoreReasoning }]">
          <span class="eyebrow">{{ assessmentFor(selectedJob.jobId)?.coarseScoreReasoning ? 'WHY THIS FITS YOU' : scoringAttemptFor(selectedJob.jobId)?.scoreError ? 'SCORING FAILED' : 'NOT SCORED FOR YOU YET' }}</span>
          <p>{{ assessmentFor(selectedJob.jobId)?.coarseScoreReasoning || scoringAttemptFor(selectedJob.jobId)?.scoreError || 'Save a scoring profile, then the scheduled scoring run will evaluate this role for your account.' }}</p>
          <small v-if="assessmentFor(selectedJob.jobId)?.scoreModel">{{ assessmentFor(selectedJob.jobId)?.scoreModel }}<template v-if="assessmentFor(selectedJob.jobId)?.scoredAt"> · {{ formatDate(assessmentFor(selectedJob.jobId)?.scoredAt ?? '') }}</template></small>
        </section>

        <section v-if="selectedJob.requiredYearsMin !== null || selectedJob.requirementKeywords.length" class="job-requirements">
          <span class="eyebrow">JOB REQUIREMENTS</span>
          <div class="requirement-tags">
            <span v-if="selectedJob.requiredYearsMin !== null" class="requirement-years">{{ yearsLabel(selectedJob.requiredYearsMin, selectedJob.requiredYearsMax) }} experience</span>
            <span v-for="keyword in selectedJob.requirementKeywords" :key="keyword" class="requirement-keyword">{{ keyword }}</span>
          </div>
        </section>

        <section class="description-section">
          <header><div><span class="eyebrow">JOB DESCRIPTION</span><small>{{ selectedJob.descriptionChars.toLocaleString() }} characters</small></div>
            <a v-if="selectedJob.primaryListing" :href="selectedJob.primaryListing.applyUrl || selectedJob.primaryListing.sourceUrl" target="_blank" rel="noopener noreferrer">Open original ↗</a>
          </header>
          <div class="description">{{ selectedJob.description || 'No description was captured for this role.' }}</div>
        </section>

        <section v-if="selectedJob.listings.length" class="sources">
          <span class="eyebrow">SOURCES</span>
          <a v-for="listing in selectedJob.listings" :key="listing.listingId" :href="listing.sourceUrl" target="_blank" rel="noopener noreferrer">
            <b>{{ sourceLabel(listing.source) }}</b><small>{{ listing.postedAtRaw || relativeDate(listing.postedAt ?? listing.firstSeenAt) }}</small><span>↗</span>
          </a>
        </section>
      </aside>
      <aside v-else-if="detailLoading" class="detail detail-loading"><n-spin size="large" /></aside>
    </section>

    <n-empty v-else-if="!loading && !loadError" description="No roles match these filters" class="empty"><template #extra><n-button @click="resetFilters">Reset filters</n-button></template></n-empty>
    <div v-else class="loading"><n-spin size="large" /></div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { jobDataSource } from '../jobs/dataSource'
import type { DashboardJob, DashboardJobSummary, DashboardRunSummary, DashboardUserState, JobUserState, JobUserStatus, ScoringQueueSummary, WorkplaceType } from '../jobs/models'

type StatusFilter = 'pending' | Exclude<JobUserStatus, 'new'>

const router = useRouter()
const jobs = ref<DashboardJobSummary[]>([])
const runs = ref<DashboardRunSummary[]>([])
const userState = ref<DashboardUserState>({ jobs: [], runs: [] })
const loading = ref(true)
const loadError = ref('')
const detailLoading = ref(false)
const selectedJobId = ref<string | null>(null)
const selectedJob = ref<DashboardJob | null>(null)
const currentProfileVersion = ref<number | null>(null)
const scoringQueue = ref<ScoringQueueSummary>({ eligibleTotal: 0, scoredCurrent: 0, pending: 0, queued: 0, failed: 0, archivedSkipped: 0 })
const queuedJobIds = ref(new Set<string>())
const search = ref('')
const category = ref('all')
const runFilter = ref('all')
const eligibility = ref('actionable')
const score = ref('all')
const freshness = ref('current')
const sort = ref('newest')
const status = ref<StatusFilter>('pending')

const categoryOptions = [{ label: 'All tracks', value: 'all' }, { label: 'SDE', value: 'sde' }, { label: 'QA', value: 'qa' }]
const eligibilityOptions = [{ label: 'Actionable roles', value: 'actionable' }, { label: 'Eligible', value: 'eligible' }, { label: 'Needs review', value: 'review' }, { label: 'Excluded', value: 'excluded' }, { label: 'All decisions', value: 'all' }]
const scoreOptions = [{ label: 'Any score', value: 'all' }, { label: 'Scored roles', value: 'scored' }, { label: 'Strong · 8+', value: 'strong' }, { label: 'Potential · 5+', value: 'potential' }, { label: 'Not scored', value: 'unscored' }]
const freshnessOptions = [{ label: 'Current roles', value: 'current' }, { label: 'Active only', value: 'active' }, { label: 'Archived', value: 'archived' }, { label: 'All ages', value: 'all' }]
const sortOptions = [{ label: 'Newest first', value: 'newest' }, { label: 'Highest score', value: 'score' }, { label: 'Company A–Z', value: 'company' }]
const runOptions = computed(() => [{ label: `All runs${unreadRunCount.value ? ` · ${unreadRunCount.value} unread` : ''}`, value: 'all' }, ...runs.value.map((run) => ({
  label: `${isRunViewed(run.runId) ? '' : '● '}${formatRun(run)} · ${run.newJobsCount} new${run.errorCount ? ` · ${run.errorCount} errors` : ''}`,
  value: run.runId,
}))])

const pendingCount = computed(() => jobs.value.filter((job) => job.eligibilityStatus !== 'excluded' && job.lifecycleStatus !== 'archived' && !['applied', 'rejected'].includes(statusFor(job.jobId))).length)
const unviewedCount = computed(() => jobs.value.filter((job) => job.eligibilityStatus !== 'excluded' && job.lifecycleStatus !== 'archived' && !isViewed(job.jobId) && !['applied', 'rejected'].includes(statusFor(job.jobId))).length)
const unreadRunCount = computed(() => runs.value.filter((run) => !isRunViewed(run.runId)).length)
const selectedRunSummary = computed(() => runFilter.value === 'all' ? runs.value[0] ?? null : runs.value.find((run) => run.runId === runFilter.value) ?? null)
const visibleJobs = computed(() => jobs.value.filter((job) => {
  const query = search.value.trim().toLowerCase()
  if (query && !`${job.title} ${job.company} ${job.location}`.toLowerCase().includes(query)) return false
  if (category.value !== 'all' && job.jobCategory !== category.value) return false
  if (runFilter.value !== 'all' && job.firstDiscoveredRunId !== runFilter.value) return false
  if (freshness.value === 'current' && job.lifecycleStatus === 'archived') return false
  if (freshness.value !== 'all' && freshness.value !== 'current' && job.lifecycleStatus !== freshness.value) return false
  if (eligibility.value === 'actionable' && job.eligibilityStatus === 'excluded') return false
  if (!['all', 'actionable'].includes(eligibility.value) && job.eligibilityStatus !== eligibility.value) return false
  if (status.value === 'pending' && ['applied', 'rejected'].includes(statusFor(job.jobId))) return false
  if (status.value !== 'pending' && statusFor(job.jobId) !== status.value) return false
  if (score.value === 'strong' && (scoreFor(job.jobId) ?? -1) < 8) return false
  if (score.value === 'potential' && (scoreFor(job.jobId) ?? -1) < 5) return false
  if (score.value === 'scored' && scoreFor(job.jobId) === null) return false
  if (score.value === 'unscored' && scoreFor(job.jobId) !== null) return false
  return true
}).sort((left, right) => {
  if (sort.value === 'score') return (scoreFor(right.jobId) ?? -1) - (scoreFor(left.jobId) ?? -1)
  if (sort.value === 'company') return left.company.localeCompare(right.company)
  return timestamp(right) - timestamp(left)
}))

const statusTabs = computed(() => {
  const count = (value: JobUserStatus): number => jobs.value.filter((job) => statusFor(job.jobId) === value).length
  return [{ label: 'Pending', value: 'pending' as const, count: pendingCount.value }, { label: 'Saved', value: 'saved' as const, count: count('saved') }, { label: 'Shortlist', value: 'selected' as const, count: count('selected') }, { label: 'Applied', value: 'applied' as const, count: count('applied') }, { label: 'Rejected', value: 'rejected' as const, count: count('rejected') }]
})

onMounted(async () => {
  try {
    const [loadedJobs, loadedRuns, loadedState, loadedProfile, loadedQueue] = await Promise.all([
      jobDataSource.listJobs(),
      jobDataSource.listRuns(),
      jobDataSource.getUserState(),
      jobDataSource.getScoringProfile(),
      jobDataSource.getScoringQueue(),
    ])
    jobs.value = loadedJobs
    runs.value = loadedRuns
    userState.value = loadedState
    currentProfileVersion.value = loadedProfile.profileVersion
    scoringQueue.value = loadedQueue
  } catch (reason) {
    loadError.value = reason instanceof Error ? reason.message : 'Unable to load jobs.'
  } finally {
    loading.value = false
  }
})

watch(visibleJobs, (items) => {
  if (!items.some((job) => job.jobId === selectedJobId.value)) selectedJobId.value = null
})

watch(runFilter, async (runId) => {
  if (runId === 'all' || isRunViewed(runId)) return
  await jobDataSource.markRunViewed(runId)
  userState.value = { ...userState.value, runs: [...userState.value.runs, { runId, viewedAt: new Date().toISOString() }] }
})

let detailRequest = 0
watch(selectedJobId, async (jobId) => {
  const request = ++detailRequest
  selectedJob.value = null
  if (!jobId) return
  detailLoading.value = true
  try {
    const job = await jobDataSource.getJob(jobId)
    if (request === detailRequest) {
      selectedJob.value = job
      if (job && !isViewed(jobId)) {
        await jobDataSource.markJobViewed(jobId)
        markJobViewedLocally(jobId)
      }
    }
  } finally {
    if (request === detailRequest) detailLoading.value = false
  }
})

function timestamp(job: DashboardJobSummary): number { return Date.parse(job.postedAt ?? job.firstSeenAt) || 0 }
function initials(company: string): string { return company.split(/\s+/).slice(0, 2).map((word) => word[0]).join('').toUpperCase() }
function workplaceLabel(value: WorkplaceType): string { return ({ remote: 'Remote', hybrid: 'Hybrid', onsite: 'On-site', unknown: 'Workplace unknown' } satisfies Record<WorkplaceType, string>)[value] }
function sourceLabel(value: string): string { return ({ workday: 'Workday', indeed: 'Indeed', linkedin: 'LinkedIn', zip_recruiter: 'ZipRecruiter' } as Record<string, string>)[value] ?? value }
function statusLabel(value: JobUserStatus): string { return ({ new: 'New', saved: 'Saved', selected: 'Shortlist', applied: 'Applied', rejected: 'Rejected' } satisfies Record<JobUserStatus, string>)[value] }
function assessmentFor(jobId: string): JobUserState | undefined {
  const assessment = stateFor(jobId)
  return assessment?.profileVersion === currentProfileVersion.value ? assessment : undefined
}
function stateFor(jobId: string): JobUserState | undefined { return userState.value.jobs.find((job) => job.jobId === jobId) }
function scoringAttemptFor(jobId: string): JobUserState | undefined {
  const state = stateFor(jobId)
  return state?.scoringProfileVersion === currentProfileVersion.value ? state : undefined
}
function scoreFor(jobId: string): number | null { return assessmentFor(jobId)?.coarseScore ?? null }
function isScoreQueued(jobId: string): boolean { return queuedJobIds.value.has(jobId) || scoringAttemptFor(jobId)?.scoringStatus === 'queued' }
function statusFor(jobId: string): JobUserStatus { return userState.value.jobs.find((job) => job.jobId === jobId)?.status ?? 'new' }
function isViewed(jobId: string): boolean { return userState.value.jobs.some((job) => job.jobId === jobId && job.firstViewedAt !== null) }
function isRunViewed(runId: string): boolean { return runId.startsWith('legacy-') || userState.value.runs.some((run) => run.runId === runId) }
function selectJob(jobId: string): void { selectedJobId.value = jobId }
function scoreClass(value: number | null): string { return value === null ? 'score-empty' : value >= 8 ? 'score-strong' : value >= 5 ? 'score-medium' : 'score-low' }
function yearsLabel(minimum: number, maximum: number | null): string {
  return maximum !== null && maximum !== minimum ? `${minimum}–${maximum} yrs` : `${minimum}+ yrs`
}
function relativeDate(value: string): string {
  const date = Date.parse(value)
  if (!Number.isFinite(date)) return 'Date unknown'
  const days = Math.max(0, Math.floor((Date.now() - date) / 86_400_000))
  return days === 0 ? 'Today' : days === 1 ? '1 day ago' : days < 30 ? `${days} days ago` : new Intl.DateTimeFormat('en-CA', { month: 'short', day: 'numeric' }).format(date)
}
function formatDate(value: string): string { return new Intl.DateTimeFormat('en-CA', { month: 'short', day: 'numeric', year: 'numeric' }).format(Date.parse(value)) }
function formatRun(run: DashboardRunSummary): string { return new Intl.DateTimeFormat('en-CA', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(Date.parse(run.discoveredAt)) }
function markJobViewedLocally(jobId: string): void {
  const now = new Date().toISOString()
  const existing = userState.value.jobs.find((job) => job.jobId === jobId)
  userState.value = { ...userState.value, jobs: [...userState.value.jobs.filter((job) => job.jobId !== jobId), {
    jobId, status: existing?.status ?? 'new', firstViewedAt: existing?.firstViewedAt ?? now, lastViewedAt: now, updatedAt: now,
    coarseScore: existing?.coarseScore ?? null, coarseScoreReasoning: existing?.coarseScoreReasoning ?? null,
    scoreModel: existing?.scoreModel ?? null, scoreVersion: existing?.scoreVersion ?? null,
    profileVersion: existing?.profileVersion ?? null, scoredAt: existing?.scoredAt ?? null,
    scoringStatus: existing?.scoringStatus ?? null, scoreError: existing?.scoreError ?? null,
    scoringProfileVersion: existing?.scoringProfileVersion ?? null,
  }] }
}
async function toggleStatus(jobId: string, value: Exclude<JobUserStatus, 'new'>): Promise<void> {
  const nextStatus: JobUserStatus = statusFor(jobId) === value ? 'new' : value
  await jobDataSource.setJobStatus(jobId, nextStatus)
  markJobViewedLocally(jobId)
  userState.value = { ...userState.value, jobs: userState.value.jobs.map((job) => job.jobId === jobId ? { ...job, status: nextStatus, updatedAt: new Date().toISOString() } : job) }
}
async function queueScore(jobId: string): Promise<void> {
  queuedJobIds.value = new Set([...queuedJobIds.value, jobId])
  try {
    await jobDataSource.scoreJob(jobId)
    scoringQueue.value = {
      ...scoringQueue.value,
      pending: Math.max(0, scoringQueue.value.pending - 1),
      queued: scoringQueue.value.queued + 1,
    }
  } catch (error) {
    queuedJobIds.value = new Set([...queuedJobIds.value].filter((value) => value !== jobId))
    throw error
  }
}
async function sendToGenerate(job: DashboardJob): Promise<void> {
  sessionStorage.setItem('job-dashboard:draft', JSON.stringify({ jobId: job.jobId, title: job.title, company: job.company, description: job.description }))
  if (statusFor(job.jobId) !== 'selected') await toggleStatus(job.jobId, 'selected')
  router.push('/generate')
}
function resetFilters(): void { search.value = ''; category.value = 'all'; runFilter.value = 'all'; eligibility.value = 'actionable'; score.value = 'all'; freshness.value = 'current'; status.value = 'pending' }
</script>

<style scoped>
.jobs-page { --panel:#12151c; --raised:#171b24; --border:rgba(255,255,255,.08); --muted:#8e98a9; min-height:calc(100vh - 56px); padding:30px 34px 48px; color:#edf1f7; background:radial-gradient(circle at 8% -15%,rgba(58,121,255,.15),transparent 32%),radial-gradient(circle at 92% 0,rgba(117,73,216,.1),transparent 28%),#0b0d12; }
.hero { display:flex; justify-content:space-between; align-items:flex-end; gap:30px; max-width:1500px; margin:0 auto 24px; }
.eyebrow { color:#6fa8ff; font:700 10px/1.3 monospace; letter-spacing:.16em; }
.hero h1 { margin:8px 0 6px; font-size:clamp(26px,3vw,40px); line-height:1.1; letter-spacing:-.035em; }
.hero p { margin:0; color:var(--muted); font-size:14px; }
.snapshot { display:flex; align-items:center; gap:10px; min-width:180px; padding:12px 15px; border:1px solid var(--border); border-radius:10px; background:rgba(18,21,28,.75); }
.snapshot i { width:8px; height:8px; border-radius:50%; background:#46d19a; box-shadow:0 0 0 4px rgba(70,209,154,.1); }
.snapshot div { display:flex; flex-direction:column; }.snapshot b{font-size:12px}.snapshot small{color:var(--muted);font-size:10px}
.filters { display:grid; grid-template-columns:minmax(250px,1fr) repeat(6,125px); gap:8px; max-width:1500px; margin:auto; padding:10px; border:1px solid var(--border); border-radius:10px; background:rgba(18,21,28,.92); }
.run-health{display:flex;align-items:center;gap:16px;max-width:1470px;margin:10px auto 0;padding:9px 14px;border:1px solid var(--border);border-radius:8px;color:#9da8b8;background:rgba(18,21,28,.7);font-size:11px}.run-health b{color:#dce3ed}.run-health strong{margin-left:auto;color:#e87783}.run-health.is-ok{border-color:rgba(75,212,157,.2)}.run-health.is-partial,.run-health.is-failed{border-color:rgba(232,119,131,.3)}
.tabs { display:flex; align-items:center; gap:4px; max-width:1500px; margin:15px auto 10px; }.tabs button{padding:7px 10px;border:0;border-radius:7px;color:var(--muted);background:transparent;font:12px inherit;cursor:pointer}.tabs button:hover,.tabs button.active{color:#edf1f7;background:#1b202b}.tabs button span{margin-left:5px;color:#687487;font-size:10px}.tabs>small{margin-left:auto;color:#687487}
.workspace { display:grid; grid-template-columns:minmax(390px,.82fr) minmax(520px,1.18fr); gap:12px; max-width:1500px; height:calc(100vh - 250px); min-height:520px; margin:auto; }
.job-list,.detail{overflow-y:auto;border:1px solid var(--border);border-radius:11px;background:rgba(18,21,28,.9)}
.detail-loading{display:grid;place-items:center}
.job-row { display:grid; grid-template-columns:38px 1fr auto; gap:12px; padding:15px; border-bottom:1px solid var(--border); cursor:pointer; }.job-row:hover{background:rgba(255,255,255,.025)}.job-row.selected{background:rgba(76,132,221,.1);box-shadow:inset 3px 0 #5d95ee}.job-row.rejected{opacity:.52}
.logo { display:grid; place-items:center; width:38px; height:38px; border:1px solid rgba(111,168,255,.24); border-radius:9px; color:#8bb8ff; background:rgba(74,125,207,.1); font:700 11px monospace; }
.row-main{min-width:0}.topline{display:flex;justify-content:space-between;gap:10px}.topline span{overflow:hidden;color:#aab3c1;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.topline small{color:#667184;font-size:10px}.job-row h2{overflow:hidden;margin:4px 0 7px;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.job-row p{margin:0;color:var(--muted);font-size:10px}.requirements{display:flex;align-items:center;gap:5px;overflow:hidden;margin-top:8px;white-space:nowrap}.requirements span{overflow:hidden;max-width:105px;padding:3px 6px;border:1px solid rgba(255,255,255,.07);border-radius:5px;color:#9da8b8;background:rgba(255,255,255,.035);font-size:9px;text-overflow:ellipsis}.requirements .years{flex:none;border-color:rgba(231,169,75,.2);color:#e7b35b;background:rgba(231,169,75,.08);font-weight:700}.requirements small{flex:none;color:#687487;font-size:9px}.job-row footer{display:flex;gap:7px;margin-top:10px}.job-row em{padding:3px 6px;border-radius:5px;font:700 9px monospace;text-transform:uppercase;font-style:normal}.is-new{color:#8bb8ff;background:rgba(74,125,207,.14)}.is-category{color:#c9a8f5;background:rgba(161,124,244,.12)}.is-eligible{color:#53d99f;background:rgba(62,207,142,.1)}.is-review{color:#edb85f;background:rgba(231,169,75,.1)}.is-excluded{color:#e47784;background:rgba(224,88,103,.1)}.user-status{color:#a58af3;background:rgba(161,124,244,.12)}.lifecycle-stale{color:#edb85f;background:rgba(231,169,75,.1)}.lifecycle-archived{color:#8993a3;background:rgba(137,147,163,.1)}
.side-col{display:flex;flex-direction:column;align-items:flex-end;gap:8px}
.quick-actions{display:flex;gap:5px}.quick-actions a,.quick-actions button{display:grid;place-items:center;width:23px;height:23px;border:1px solid var(--border);border-radius:6px;color:var(--muted);background:rgba(255,255,255,.03);font-size:12px;line-height:1;text-decoration:none;cursor:pointer}.quick-actions a:hover,.quick-actions button:hover{color:#edf1f7;background:#1b202b}.quick-actions button.active{color:#e47784;border-color:rgba(224,88,103,.35);background:rgba(224,88,103,.1)}
.score{display:flex;flex-direction:column;align-items:flex-end;min-width:39px}.score b{font-size:19px}.score small{color:#606a7b;font-size:8px}.score-strong{color:#4bd49d}.score-medium{color:#e9b65e}.score-low{color:#e87783}.score-empty{color:#5f6979}
.detail{padding:23px 25px 30px}.detail>header{display:flex;justify-content:space-between;gap:20px}.detail>header span{color:#8eb8f6;font-size:12px}.detail h2{margin:5px 0 7px;font-size:23px}.detail header p{margin:0;color:var(--muted);font-size:12px}.detail-score{display:flex;flex:none;flex-direction:column;align-items:center;justify-content:center;width:69px;height:61px;border:1px solid currentColor;border-radius:10px}.detail-score b{font-size:24px}.detail-score small{color:#707b8d;font-size:8px;text-transform:uppercase}.actions{display:flex;gap:8px;margin:20px 0;padding-bottom:20px;border-bottom:1px solid var(--border)}.generate{margin-left:auto}
.reasoning{margin-bottom:23px;padding:15px 17px;border:1px solid rgba(93,149,238,.18);border-radius:9px;background:rgba(65,109,178,.07)}.reasoning.pending{border-color:rgba(231,169,75,.18);background:rgba(231,169,75,.05)}.reasoning p{margin:7px 0 9px;color:#bac3d1;font-size:12px;line-height:1.65}.reasoning small{color:#626e80;font:9px monospace}
.job-requirements{margin-bottom:23px}.requirement-tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}.requirement-tags span{padding:5px 8px;border:1px solid rgba(255,255,255,.08);border-radius:6px;color:#aeb8c7;background:rgba(255,255,255,.035);font-size:10px;line-height:1.3}.requirement-tags .requirement-years{border-color:rgba(231,169,75,.22);color:#e8b760;background:rgba(231,169,75,.08);font-weight:700}
.description-section>header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:13px}.description-section>header div{display:flex;flex-direction:column;gap:4px}.description-section header small{color:#7d8797}.description-section a{color:#79aaf2;font-size:11px;text-decoration:none}.description{max-height:380px;overflow-y:auto;padding:16px;border:1px solid var(--border);border-radius:9px;color:#b5becb;background:#0e1117;font-size:12px;line-height:1.65;white-space:pre-wrap}
.sources{margin-top:23px}.sources>a{display:grid;grid-template-columns:100px 1fr auto;gap:12px;margin-top:8px;padding:10px 12px;border:1px solid var(--border);border-radius:7px;color:#b6bfcc;text-decoration:none}.sources a small{color:#6f7989}.sources a span{color:#78aaf3}
.empty,.loading{display:grid;place-items:center;max-width:1500px;height:420px;margin:auto;border:1px solid var(--border);border-radius:11px;background:rgba(18,21,28,.8)}
.load-error{max-width:1500px;margin:16px auto}
@media(max-width:1050px){.jobs-page{padding:24px 18px}.filters{grid-template-columns:repeat(2,1fr)}.search{grid-column:1/-1}.workspace{grid-template-columns:1fr;height:auto}.job-list{max-height:540px}}
@media(max-width:640px){.hero{align-items:flex-start;flex-direction:column}.snapshot{width:100%;box-sizing:border-box}.filters{grid-template-columns:1fr 1fr}.actions{flex-wrap:wrap}.generate{width:100%;margin-left:0}.score{display:none}}
</style>
