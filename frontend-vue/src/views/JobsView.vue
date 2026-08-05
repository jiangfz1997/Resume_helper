<template>
  <main class="jobs-page">
    <header class="hero">
      <div>
        <span class="eyebrow">JOB DISCOVERY / LOCAL SNAPSHOT</span>
        <h1>Your next role, without the noise.</h1>
        <p>Review discovered roles, understand their coarse score, and build a focused shortlist.</p>
      </div>
      <div class="snapshot"><i /><div><b>{{ jobs.length }} roles loaded</b><small>Static DynamoDB export</small></div></div>
    </header>

    <section class="metrics">
      <div><span>Eligible</span><b>{{ eligibleCount }}</b><small>Passed hard filters</small></div>
      <div><span>Strong matches</span><b>{{ strongCount }}</b><small>Score 8 or higher</small></div>
      <div><span>Needs review</span><b>{{ reviewCount }}</b><small>Missing or uncertain data</small></div>
      <div><span>Shortlisted</span><b>{{ shortlistCount }}</b><small>Saved on this browser</small></div>
    </section>

    <section class="filters">
      <n-input v-model:value="search" clearable placeholder="Search title, company, or location..." class="search" />
      <n-select v-model:value="eligibility" :options="eligibilityOptions" />
      <n-select v-model:value="workplace" :options="workplaceOptions" />
      <n-select v-model:value="source" :options="sourceOptions" />
      <n-select v-model:value="score" :options="scoreOptions" />
      <n-select v-model:value="sort" :options="sortOptions" />
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
          :class="['job-row', { selected: selectedJobId === job.jobId, rejected: jobsStore.statusFor(job.jobId) === 'rejected' }]"
          @click="selectedJobId = job.jobId"
        >
          <div class="logo">{{ initials(job.company) }}</div>
          <div class="row-main">
            <div class="topline"><span>{{ job.company }}</span><small>{{ relativeDate(job.postedAt ?? job.firstSeenAt) }}</small></div>
            <h2>{{ job.title }}</h2>
            <p>{{ job.location }} · {{ workplaceLabel(job.workplaceType) }}<template v-if="job.sources[0]"> · {{ sourceLabel(job.sources[0]) }}</template></p>
            <footer>
              <em :class="`is-${job.eligibilityStatus}`">{{ job.eligibilityStatus }}</em>
              <em v-if="jobsStore.statusFor(job.jobId) !== 'new'" class="user-status">{{ statusLabel(jobsStore.statusFor(job.jobId)) }}</em>
            </footer>
          </div>
          <div :class="['score', scoreClass(job.coarseScore)]"><b>{{ job.coarseScore ?? '—' }}</b><small>/ 10</small></div>
        </article>
      </div>

      <aside v-if="selectedJob" class="detail">
        <header>
          <div><span>{{ selectedJob.company }}</span><h2>{{ selectedJob.title }}</h2><p>{{ selectedJob.location }} · {{ workplaceLabel(selectedJob.workplaceType) }}</p></div>
          <div :class="['detail-score', scoreClass(selectedJob.coarseScore)]"><b>{{ selectedJob.coarseScore ?? '—' }}</b><small>coarse fit</small></div>
        </header>

        <div class="actions">
          <n-button :type="jobsStore.statusFor(selectedJob.jobId) === 'saved' ? 'primary' : 'default'" @click="toggleStatus(selectedJob.jobId, 'saved')">{{ jobsStore.statusFor(selectedJob.jobId) === 'saved' ? 'Saved' : 'Save role' }}</n-button>
          <n-button :type="jobsStore.statusFor(selectedJob.jobId) === 'selected' ? 'success' : 'default'" @click="toggleStatus(selectedJob.jobId, 'selected')">{{ jobsStore.statusFor(selectedJob.jobId) === 'selected' ? 'In shortlist' : 'Shortlist' }}</n-button>
          <n-button quaternary type="error" @click="toggleStatus(selectedJob.jobId, 'rejected')">{{ jobsStore.statusFor(selectedJob.jobId) === 'rejected' ? 'Restore' : 'Reject' }}</n-button>
          <n-button type="primary" class="generate" @click="sendToGenerate(selectedJob)">Generate resume</n-button>
        </div>

        <section :class="['reasoning', { pending: !selectedJob.coarseScoreReasoning }]">
          <span class="eyebrow">{{ selectedJob.coarseScoreReasoning ? 'WHY THIS SCORE' : 'NOT SCORED YET' }}</span>
          <p>{{ selectedJob.coarseScoreReasoning || 'This role passed discovery but has not been through the coarse scoring stage.' }}</p>
          <small v-if="selectedJob.scoreModel">{{ selectedJob.scoreModel }}<template v-if="selectedJob.scoredAt"> · {{ formatDate(selectedJob.scoredAt) }}</template></small>
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
import type { DashboardJob, DashboardJobSummary, JobUserStatus, WorkplaceType } from '../jobs/models'
import { useJobsStore } from '../stores/jobs'

type StatusFilter = 'all' | JobUserStatus

const router = useRouter()
const jobsStore = useJobsStore()
const jobs = ref<DashboardJobSummary[]>([])
const loading = ref(true)
const loadError = ref('')
const detailLoading = ref(false)
const selectedJobId = ref<string | null>(null)
const selectedJob = ref<DashboardJob | null>(null)
const search = ref('')
const eligibility = ref('all')
const workplace = ref('all')
const source = ref('all')
const score = ref('all')
const sort = ref('newest')
const status = ref<StatusFilter>('all')

const eligibilityOptions = [{ label: 'All decisions', value: 'all' }, { label: 'Eligible', value: 'eligible' }, { label: 'Needs review', value: 'review' }, { label: 'Excluded', value: 'excluded' }]
const workplaceOptions = [{ label: 'All workplaces', value: 'all' }, { label: 'Remote', value: 'remote' }, { label: 'Hybrid', value: 'hybrid' }, { label: 'On-site', value: 'onsite' }, { label: 'Unknown', value: 'unknown' }]
const scoreOptions = [{ label: 'Any score', value: 'all' }, { label: 'Strong · 8+', value: 'strong' }, { label: 'Potential · 5+', value: 'potential' }, { label: 'Not scored', value: 'unscored' }]
const sortOptions = [{ label: 'Newest first', value: 'newest' }, { label: 'Highest score', value: 'score' }, { label: 'Company A–Z', value: 'company' }]
const sourceOptions = computed(() => [{ label: 'All sources', value: 'all' }, ...Array.from(new Set(jobs.value.flatMap((job) => job.sources))).sort().map((value) => ({ label: sourceLabel(value), value }))])

const eligibleCount = computed(() => jobs.value.filter((job) => job.eligibilityStatus === 'eligible').length)
const reviewCount = computed(() => jobs.value.filter((job) => job.eligibilityStatus === 'review').length)
const strongCount = computed(() => jobs.value.filter((job) => (job.coarseScore ?? -1) >= 8).length)
const shortlistCount = computed(() => jobs.value.filter((job) => jobsStore.statusFor(job.jobId) === 'selected').length)
const visibleJobs = computed(() => jobs.value.filter((job) => {
  const query = search.value.trim().toLowerCase()
  if (query && !`${job.title} ${job.company} ${job.location}`.toLowerCase().includes(query)) return false
  if (eligibility.value !== 'all' && job.eligibilityStatus !== eligibility.value) return false
  if (workplace.value !== 'all' && job.workplaceType !== workplace.value) return false
  if (source.value !== 'all' && !job.sources.includes(source.value)) return false
  if (status.value !== 'all' && jobsStore.statusFor(job.jobId) !== status.value) return false
  if (score.value === 'strong' && (job.coarseScore ?? -1) < 8) return false
  if (score.value === 'potential' && (job.coarseScore ?? -1) < 5) return false
  if (score.value === 'unscored' && job.coarseScore !== null) return false
  return true
}).sort((left, right) => {
  if (sort.value === 'score') return (right.coarseScore ?? -1) - (left.coarseScore ?? -1)
  if (sort.value === 'company') return left.company.localeCompare(right.company)
  return timestamp(right) - timestamp(left)
}))

const statusTabs = computed(() => {
  const count = (value: JobUserStatus): number => jobs.value.filter((job) => jobsStore.statusFor(job.jobId) === value).length
  return [{ label: 'All roles', value: 'all' as const, count: jobs.value.length }, { label: 'Saved', value: 'saved' as const, count: count('saved') }, { label: 'Shortlist', value: 'selected' as const, count: count('selected') }, { label: 'Rejected', value: 'rejected' as const, count: count('rejected') }]
})

onMounted(async () => {
  try {
    jobs.value = await jobDataSource.listJobs()
    selectedJobId.value = jobs.value[0]?.jobId ?? null
  } catch (reason) {
    loadError.value = reason instanceof Error ? reason.message : 'Unable to load jobs.'
  } finally {
    loading.value = false
  }
})

watch(visibleJobs, (items) => {
  if (!items.some((job) => job.jobId === selectedJobId.value)) selectedJobId.value = items[0]?.jobId ?? null
})

let detailRequest = 0
watch(selectedJobId, async (jobId) => {
  const request = ++detailRequest
  selectedJob.value = null
  if (!jobId) return
  detailLoading.value = true
  try {
    const job = await jobDataSource.getJob(jobId)
    if (request === detailRequest) selectedJob.value = job
  } finally {
    if (request === detailRequest) detailLoading.value = false
  }
})

function timestamp(job: DashboardJobSummary): number { return Date.parse(job.postedAt ?? job.firstSeenAt) || 0 }
function initials(company: string): string { return company.split(/\s+/).slice(0, 2).map((word) => word[0]).join('').toUpperCase() }
function workplaceLabel(value: WorkplaceType): string { return ({ remote: 'Remote', hybrid: 'Hybrid', onsite: 'On-site', unknown: 'Workplace unknown' } satisfies Record<WorkplaceType, string>)[value] }
function sourceLabel(value: string): string { return ({ workday: 'Workday', indeed: 'Indeed', linkedin: 'LinkedIn', zip_recruiter: 'ZipRecruiter' } as Record<string, string>)[value] ?? value }
function statusLabel(value: JobUserStatus): string { return ({ new: 'New', saved: 'Saved', selected: 'Shortlist', rejected: 'Rejected' } satisfies Record<JobUserStatus, string>)[value] }
function scoreClass(value: number | null): string { return value === null ? 'score-empty' : value >= 8 ? 'score-strong' : value >= 5 ? 'score-medium' : 'score-low' }
function relativeDate(value: string): string {
  const date = Date.parse(value)
  if (!Number.isFinite(date)) return 'Date unknown'
  const days = Math.max(0, Math.floor((Date.now() - date) / 86_400_000))
  return days === 0 ? 'Today' : days === 1 ? '1 day ago' : days < 30 ? `${days} days ago` : new Intl.DateTimeFormat('en-CA', { month: 'short', day: 'numeric' }).format(date)
}
function formatDate(value: string): string { return new Intl.DateTimeFormat('en-CA', { month: 'short', day: 'numeric', year: 'numeric' }).format(Date.parse(value)) }
function toggleStatus(jobId: string, value: Exclude<JobUserStatus, 'new'>): void { jobsStore.setStatus(jobId, jobsStore.statusFor(jobId) === value ? 'new' : value) }
function sendToGenerate(job: DashboardJob): void {
  sessionStorage.setItem('job-dashboard:draft', JSON.stringify({ jobId: job.jobId, title: job.title, company: job.company, description: job.description }))
  jobsStore.setStatus(job.jobId, 'selected')
  router.push('/generate')
}
function resetFilters(): void { search.value = ''; eligibility.value = 'all'; workplace.value = 'all'; source.value = 'all'; score.value = 'all'; status.value = 'all' }
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
.metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; max-width:1500px; margin:0 auto 18px; }
.metrics>div { display:grid; gap:3px; padding:15px 17px; border:1px solid var(--border); border-left:3px solid #5d95ee; border-radius:10px; background:rgba(18,21,28,.9); }
.metrics>div:nth-child(2){border-left-color:#3ecf8e}.metrics>div:nth-child(3){border-left-color:#e7a94b}.metrics>div:nth-child(4){border-left-color:#a17cf4}
.metrics span { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.07em; }.metrics b{font-size:25px}.metrics small{color:#697386;font-size:10px}
.filters { display:grid; grid-template-columns:minmax(250px,1fr) repeat(5,148px); gap:8px; max-width:1500px; margin:auto; padding:10px; border:1px solid var(--border); border-radius:10px; background:rgba(18,21,28,.92); }
.tabs { display:flex; align-items:center; gap:4px; max-width:1500px; margin:15px auto 10px; }.tabs button{padding:7px 10px;border:0;border-radius:7px;color:var(--muted);background:transparent;font:12px inherit;cursor:pointer}.tabs button:hover,.tabs button.active{color:#edf1f7;background:#1b202b}.tabs button span{margin-left:5px;color:#687487;font-size:10px}.tabs>small{margin-left:auto;color:#687487}
.workspace { display:grid; grid-template-columns:minmax(390px,.82fr) minmax(520px,1.18fr); gap:12px; max-width:1500px; height:calc(100vh - 341px); min-height:520px; margin:auto; }
.job-list,.detail{overflow-y:auto;border:1px solid var(--border);border-radius:11px;background:rgba(18,21,28,.9)}
.detail-loading{display:grid;place-items:center}
.job-row { display:grid; grid-template-columns:38px 1fr auto; gap:12px; padding:15px; border-bottom:1px solid var(--border); cursor:pointer; }.job-row:hover{background:rgba(255,255,255,.025)}.job-row.selected{background:rgba(76,132,221,.1);box-shadow:inset 3px 0 #5d95ee}.job-row.rejected{opacity:.52}
.logo { display:grid; place-items:center; width:38px; height:38px; border:1px solid rgba(111,168,255,.24); border-radius:9px; color:#8bb8ff; background:rgba(74,125,207,.1); font:700 11px monospace; }
.row-main{min-width:0}.topline{display:flex;justify-content:space-between;gap:10px}.topline span{overflow:hidden;color:#aab3c1;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.topline small{color:#667184;font-size:10px}.job-row h2{overflow:hidden;margin:4px 0 7px;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.job-row p{margin:0;color:var(--muted);font-size:10px}.job-row footer{display:flex;gap:7px;margin-top:10px}.job-row em{padding:3px 6px;border-radius:5px;font:700 9px monospace;text-transform:uppercase;font-style:normal}.is-eligible{color:#53d99f;background:rgba(62,207,142,.1)}.is-review{color:#edb85f;background:rgba(231,169,75,.1)}.is-excluded{color:#e47784;background:rgba(224,88,103,.1)}.user-status{color:#a58af3;background:rgba(161,124,244,.12)}
.score{display:flex;flex-direction:column;align-items:flex-end;min-width:39px}.score b{font-size:19px}.score small{color:#606a7b;font-size:8px}.score-strong{color:#4bd49d}.score-medium{color:#e9b65e}.score-low{color:#e87783}.score-empty{color:#5f6979}
.detail{padding:23px 25px 30px}.detail>header{display:flex;justify-content:space-between;gap:20px}.detail>header span{color:#8eb8f6;font-size:12px}.detail h2{margin:5px 0 7px;font-size:23px}.detail header p{margin:0;color:var(--muted);font-size:12px}.detail-score{display:flex;flex:none;flex-direction:column;align-items:center;justify-content:center;width:69px;height:61px;border:1px solid currentColor;border-radius:10px}.detail-score b{font-size:24px}.detail-score small{color:#707b8d;font-size:8px;text-transform:uppercase}.actions{display:flex;gap:8px;margin:20px 0;padding-bottom:20px;border-bottom:1px solid var(--border)}.generate{margin-left:auto}
.reasoning{margin-bottom:23px;padding:15px 17px;border:1px solid rgba(93,149,238,.18);border-radius:9px;background:rgba(65,109,178,.07)}.reasoning.pending{border-color:rgba(231,169,75,.18);background:rgba(231,169,75,.05)}.reasoning p{margin:7px 0 9px;color:#bac3d1;font-size:12px;line-height:1.65}.reasoning small{color:#626e80;font:9px monospace}
.description-section>header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:13px}.description-section>header div{display:flex;flex-direction:column;gap:4px}.description-section header small{color:#7d8797}.description-section a{color:#79aaf2;font-size:11px;text-decoration:none}.description{max-height:380px;overflow-y:auto;padding:16px;border:1px solid var(--border);border-radius:9px;color:#b5becb;background:#0e1117;font-size:12px;line-height:1.65;white-space:pre-wrap}
.sources{margin-top:23px}.sources>a{display:grid;grid-template-columns:100px 1fr auto;gap:12px;margin-top:8px;padding:10px 12px;border:1px solid var(--border);border-radius:7px;color:#b6bfcc;text-decoration:none}.sources a small{color:#6f7989}.sources a span{color:#78aaf3}
.empty,.loading{display:grid;place-items:center;max-width:1500px;height:420px;margin:auto;border:1px solid var(--border);border-radius:11px;background:rgba(18,21,28,.8)}
.load-error{max-width:1500px;margin:16px auto}
@media(max-width:1050px){.jobs-page{padding:24px 18px}.metrics{grid-template-columns:repeat(2,1fr)}.filters{grid-template-columns:repeat(3,1fr)}.search{grid-column:1/-1}.workspace{grid-template-columns:1fr;height:auto}.job-list{max-height:540px}}
@media(max-width:640px){.hero{align-items:flex-start;flex-direction:column}.snapshot{width:100%;box-sizing:border-box}.filters{grid-template-columns:1fr 1fr}.actions{flex-wrap:wrap}.generate{width:100%;margin-left:0}.score{display:none}}
</style>
