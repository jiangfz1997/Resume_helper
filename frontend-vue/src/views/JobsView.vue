<template>
  <main class="jobs-page">
    <header class="hero">
      <div>
        <span class="eyebrow">{{ auth.isAuthenticated ? 'JOB DISCOVERY / PERSONAL INBOX' : 'JOB DISCOVERY / PUBLIC READ-ONLY DEMO' }}</span>
        <h1>Your next role, without the noise.</h1>
        <p>Review discovered roles, understand their coarse score, and build a focused shortlist.</p>
      </div>
      <div class="snapshot"><i /><div>
        <template v-if="auth.isAuthenticated"><b>{{ pendingCount }} pending · {{ unreadRunCount }} unread runs</b><small>{{ scoringQueue.scoredCurrent }} scored · {{ scoringQueue.pending }} waiting · {{ scoringQueue.queued }} queued · {{ scoringQueue.failed }} failed · {{ unviewedCount }} unopened</small></template>
        <template v-else><b>{{ jobs.length }} public roles</b><small>Read-only portfolio view</small></template>
      </div></div>
    </header>

    <section class="filters">
      <n-input v-model:value="search" clearable placeholder="Search title, company, or location..." class="search" />
      <n-select v-model:value="category" :options="categoryOptions" />
      <n-select v-model:value="runFilter" :options="runOptions" />
      <n-select v-model:value="eligibility" :options="eligibilityOptions" />
      <n-select v-if="auth.isAuthenticated" v-model:value="score" :options="scoreOptions" />
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
            <div v-if="job.isNewGrad || job.requiredYearsMin !== null || job.requirementKeywords.length" class="requirements">
              <span v-if="job.isNewGrad" class="new-grad" :title="job.newGradSignals.join(', ')">new grad</span>
              <span v-if="job.requiredYearsMin !== null" class="years">{{ yearsLabel(job.requiredYearsMin, job.requiredYearsMax) }}</span>
              <span v-for="keyword in job.requirementKeywords.slice(0, 4)" :key="keyword" class="keyword" :title="keyword">{{ keyword }}</span>
              <small v-if="job.requirementKeywords.length > 4">+{{ job.requirementKeywords.length - 4 }}</small>
            </div>
            <footer>
              <em v-if="job.jobCategory" class="is-category">{{ job.jobCategory.toUpperCase() }}</em>
              <em v-if="auth.isAuthenticated && !isViewed(job.jobId)" class="is-new">new</em>
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
                v-if="auth.isAuthenticated"
                :class="{ active: statusFor(job.jobId) === 'rejected' }"
                :title="statusFor(job.jobId) === 'rejected' ? 'Restore' : 'Not interested'"
                @click.stop="toggleStatus(job.jobId, 'rejected')"
              >{{ statusFor(job.jobId) === 'rejected' ? '↩' : '✕' }}</button>
              <button
                v-if="auth.isAuthenticated"
                :title="`Block ${job.company} — hide every current and future posting`"
                @click.stop="blockCompany(job.company)"
              >⊘</button>
            </div>
            <div
              v-if="auth.isAuthenticated"
              :class="['score', scoreClass(scoreFor(job.jobId)), { stale: isStaleScore(job.jobId) }]"
              :title="isStaleScore(job.jobId) ? `Scored under ${staleLabel(job.jobId)}; yours is now v${currentProfileVersion}` : undefined"
            ><b>{{ scoreFor(job.jobId) ?? '—' }}</b><small>{{ isStaleScore(job.jobId) ? 'older' : '/ 10' }}</small></div>
          </div>
        </article>
      </div>

      <aside v-if="selectedJob" class="detail">
        <header>
          <div><span>{{ selectedJob.company }}</span><h2>{{ selectedJob.title }}</h2><p>{{ selectedJob.location }} · {{ workplaceLabel(selectedJob.workplaceType) }}</p></div>
          <div v-if="auth.isAuthenticated" :class="['detail-score', scoreClass(scoreFor(selectedJob.jobId)), { stale: isStaleScore(selectedJob.jobId) }]"><b>{{ scoreFor(selectedJob.jobId) ?? '—' }}</b><small>{{ isStaleScore(selectedJob.jobId) ? staleLabel(selectedJob.jobId) : 'your fit' }}</small></div>
        </header>

        <div v-if="auth.isAuthenticated" class="actions">
          <n-button :type="statusFor(selectedJob.jobId) === 'saved' ? 'primary' : 'default'" @click="toggleStatus(selectedJob.jobId, 'saved')">{{ statusFor(selectedJob.jobId) === 'saved' ? 'Saved' : 'Save role' }}</n-button>
          <n-button :type="statusFor(selectedJob.jobId) === 'selected' ? 'success' : 'default'" @click="toggleStatus(selectedJob.jobId, 'selected')">{{ statusFor(selectedJob.jobId) === 'selected' ? 'In shortlist' : 'Shortlist' }}</n-button>
          <n-button :type="statusFor(selectedJob.jobId) === 'applied' ? 'success' : 'default'" @click="toggleStatus(selectedJob.jobId, 'applied')">{{ statusFor(selectedJob.jobId) === 'applied' ? 'Applied' : 'Mark applied' }}</n-button>
          <n-button quaternary type="error" @click="toggleStatus(selectedJob.jobId, 'rejected')">{{ statusFor(selectedJob.jobId) === 'rejected' ? 'Restore' : 'Reject' }}</n-button>
          <n-button quaternary type="error" @click="blockCompany(selectedJob.company)">Block company</n-button>
          <n-button v-if="scoreFor(selectedJob.jobId) === null || isStaleScore(selectedJob.jobId)" :disabled="isScoreQueued(selectedJob.jobId)" @click="queueScore(selectedJob.jobId)">{{ isScoreQueued(selectedJob.jobId) ? 'Queued' : scoringAttemptFor(selectedJob.jobId)?.scoringStatus === 'failed' ? 'Retry score' : isStaleScore(selectedJob.jobId) ? 'Rescore' : 'Score now' }}</n-button>
          <n-button type="primary" class="generate" @click="sendToGenerate(selectedJob)">Generate resume</n-button>
        </div>

        <div v-else class="actions public-actions">
          <n-button v-if="selectedJob.primaryListing" tag="a" :href="selectedJob.primaryListing.applyUrl || selectedJob.primaryListing.sourceUrl" target="_blank">Open original</n-button>
          <n-button type="primary" @click="router.push('/auth')">Owner sign in</n-button>
        </div>

        <section v-if="auth.isAuthenticated" :class="['reasoning', { pending: !assessmentFor(selectedJob.jobId)?.coarseScoreReasoning }]">
          <span class="eyebrow">{{ reasoningEyebrow(selectedJob.jobId) }}</span>
          <p>{{ assessmentFor(selectedJob.jobId)?.coarseScoreReasoning || scoringAttemptFor(selectedJob.jobId)?.scoreError || 'Save a scoring profile, then the scheduled scoring run will evaluate this role for your account.' }}</p>
          <small v-if="assessmentFor(selectedJob.jobId)?.scoreModel">{{ assessmentFor(selectedJob.jobId)?.scoreModel }}<template v-if="assessmentFor(selectedJob.jobId)?.scoredAt"> · {{ formatDate(assessmentFor(selectedJob.jobId)?.scoredAt ?? '') }}</template></small>
        </section>

        <section v-if="selectedJob.isNewGrad || selectedJob.requiredYearsMin !== null || selectedJob.requirementKeywords.length" class="job-requirements">
          <span class="eyebrow">JOB REQUIREMENTS</span>
          <div class="requirement-tags">
            <span v-if="selectedJob.isNewGrad" class="requirement-new-grad" :title="`matched: ${selectedJob.newGradSignals.join(', ')}`">new grad</span>
            <span v-if="selectedJob.requiredYearsMin !== null" class="requirement-years">{{ yearsLabel(selectedJob.requiredYearsMin, selectedJob.requiredYearsMax) }} experience</span>
            <span v-for="keyword in selectedJob.requirementKeywords" :key="keyword" class="requirement-keyword">{{ keyword }}</span>
          </div>
        </section>

        <section class="description-section">
          <div class="description-heading">
            <button
              class="description-toggle"
              type="button"
              :aria-expanded="descriptionExpanded"
              aria-controls="full-job-description"
              @click="descriptionExpanded = !descriptionExpanded"
            >
              <span class="description-title">
                <span class="eyebrow">FULL JOB POSTING</span>
                <small>{{ selectedJob.descriptionChars.toLocaleString() }} characters · archived original</small>
              </span>
              <span class="description-toggle-label">{{ descriptionExpanded ? 'Hide' : 'View' }} <i aria-hidden="true">⌄</i></span>
            </button>
            <a v-if="selectedJob.primaryListing" :href="selectedJob.primaryListing.applyUrl || selectedJob.primaryListing.sourceUrl" target="_blank" rel="noopener noreferrer">Open original ↗</a>
          </div>
          <div v-if="descriptionExpanded" id="full-job-description" class="description">
            <template v-if="descriptionBlocks.length">
              <template v-for="(block, index) in descriptionBlocks" :key="`${block.type}-${index}`">
                <h3 v-if="block.type === 'heading'">{{ block.text }}</h3>
                <ul v-else-if="block.type === 'list'">
                  <li v-for="item in block.items" :key="item">{{ item }}</li>
                </ul>
                <p v-else>{{ block.text }}</p>
              </template>
            </template>
            <p v-else class="description-empty">No description was captured for this role.</p>
          </div>
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
import { useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { applicationDataSource } from '../applications/dataSource'
import { normalizeCompany } from '../jobs/company'
import { jobDataSource } from '../jobs/dataSource'
import type { DashboardJob, DashboardJobSummary, DashboardRunSummary, DashboardUserState, JobUserState, JobUserStatus, ScoringQueueSummary, WorkplaceType } from '../jobs/models'
import { useAuthStore } from '../stores/auth'

type StatusFilter = 'pending' | Exclude<JobUserStatus, 'new'>
type DescriptionBlock =
  | { type: 'heading' | 'paragraph'; text: string }
  | { type: 'list'; items: string[] }

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()
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
const blockedCompanies = ref(new Set<string>())
const search = ref('')
const category = ref('all')
const runFilter = ref('all')
const eligibility = ref('actionable')
const score = ref('all')
const freshness = ref('current')
const sort = ref('newest')
const status = ref<StatusFilter>('pending')
const descriptionExpanded = ref(false)

const categoryOptions = [{ label: 'All tracks', value: 'all' }, { label: 'SDE', value: 'sde' }, { label: 'QA', value: 'qa' }]
const eligibilityOptions = [{ label: 'Actionable roles', value: 'actionable' }, { label: 'Eligible', value: 'eligible' }, { label: 'Needs review', value: 'review' }, { label: 'Excluded', value: 'excluded' }, { label: 'All decisions', value: 'all' }]
const scoreOptions = [{ label: 'Any score', value: 'all' }, { label: 'Scored roles', value: 'scored' }, { label: 'Strong · 8+', value: 'strong' }, { label: 'Potential · 5+', value: 'potential' }, { label: 'Not scored', value: 'unscored' }]
const freshnessOptions = [{ label: 'Current roles', value: 'current' }, { label: 'Active only', value: 'active' }, { label: 'Archived', value: 'archived' }, { label: 'All ages', value: 'all' }]
const sortOptions = [{ label: 'Newest first', value: 'newest' }, { label: 'Highest score', value: 'score' }, { label: 'Company A–Z', value: 'company' }]
const runOptions = computed(() => [{ label: `All runs${unreadRunCount.value ? ` · ${unreadRunCount.value} unread` : ''}`, value: 'all' }, ...runs.value.map((run) => ({
  label: `${isRunViewed(run.runId) ? '' : '● '}${formatRun(run)} · ${run.newJobsCount} new${run.errorCount ? ` · ${run.errorCount} errors` : ''}`,
  value: run.runId,
}))])

// Everything the filter bar selects, before the status tabs narrow it down.
// Kept separate so the tab counts can describe the set the tabs are choosing
// between: counting the whole inbox made "Pending 235" while a single run was
// selected, which described no view the user could reach.
const filteredJobs = computed(() => jobs.value.filter((job) => {
  // The API already drops blocked companies; this keeps a freshly blocked one
  // from lingering until the next page load.
  if (blockedCompanies.value.has(normalizeCompany(job.company))) return false
  const query = search.value.trim().toLowerCase()
  if (query && !`${job.title} ${job.company} ${job.location}`.toLowerCase().includes(query)) return false
  if (category.value !== 'all' && job.jobCategory !== category.value) return false
  if (runFilter.value !== 'all' && job.firstDiscoveredRunId !== runFilter.value) return false
  if (freshness.value === 'current' && job.lifecycleStatus === 'archived') return false
  if (freshness.value !== 'all' && freshness.value !== 'current' && job.lifecycleStatus !== freshness.value) return false
  if (eligibility.value === 'actionable' && job.eligibilityStatus === 'excluded') return false
  if (!['all', 'actionable'].includes(eligibility.value) && job.eligibilityStatus !== eligibility.value) return false
  if (score.value === 'strong' && (scoreFor(job.jobId) ?? -1) < 8) return false
  if (score.value === 'potential' && (scoreFor(job.jobId) ?? -1) < 5) return false
  if (score.value === 'scored' && scoreFor(job.jobId) === null) return false
  if (score.value === 'unscored' && scoreFor(job.jobId) !== null) return false
  return true
}))

// No eligibility/lifecycle guards here any more: the filter bar owns those two
// dimensions, and repeating them would make "Pending 0" sit above a populated
// list as soon as the Excluded or Archived filter is selected.
const pendingCount = computed(() => filteredJobs.value.filter((job) => !['applied', 'rejected'].includes(statusFor(job.jobId))).length)
const unviewedCount = computed(() => filteredJobs.value.filter((job) => !isViewed(job.jobId) && !['applied', 'rejected'].includes(statusFor(job.jobId))).length)
const unreadRunCount = computed(() => runs.value.filter((run) => !isRunViewed(run.runId)).length)
const selectedRunSummary = computed(() => runFilter.value === 'all' ? runs.value[0] ?? null : runs.value.find((run) => run.runId === runFilter.value) ?? null)
const visibleJobs = computed(() => filteredJobs.value.filter((job) => {
  if (status.value === 'pending') return !['applied', 'rejected'].includes(statusFor(job.jobId))
  return statusFor(job.jobId) === status.value
}).sort((left, right) => {
  if (sort.value === 'score') return (scoreFor(right.jobId) ?? -1) - (scoreFor(left.jobId) ?? -1)
  if (sort.value === 'company') return left.company.localeCompare(right.company)
  return timestamp(right) - timestamp(left)
}))

const statusTabs = computed(() => {
  if (!auth.isAuthenticated) return [{ label: 'All roles', value: 'pending' as const, count: filteredJobs.value.length }]
  const count = (value: JobUserStatus): number => filteredJobs.value.filter((job) => statusFor(job.jobId) === value).length
  return [{ label: 'Pending', value: 'pending' as const, count: pendingCount.value }, { label: 'Saved', value: 'saved' as const, count: count('saved') }, { label: 'Shortlist', value: 'selected' as const, count: count('selected') }, { label: 'Applied', value: 'applied' as const, count: count('applied') }, { label: 'Rejected', value: 'rejected' as const, count: count('rejected') }]
})
const descriptionBlocks = computed<DescriptionBlock[]>(() => formatDescription(selectedJob.value?.description ?? ''))

onMounted(async () => {
  try {
    const bootstrap = await jobDataSource.getBootstrap()
    jobs.value = bootstrap.jobs
    runs.value = bootstrap.runs
    userState.value = bootstrap.userState
    currentProfileVersion.value = bootstrap.scoringProfile.profileVersion
    scoringQueue.value = bootstrap.scoringQueue
    blockedCompanies.value = new Set(bootstrap.blockedCompanies)
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
  if (!auth.isAuthenticated || runId === 'all' || isRunViewed(runId)) return
  await jobDataSource.markRunViewed(runId)
  userState.value = { ...userState.value, runs: [...userState.value.runs, { runId, viewedAt: new Date().toISOString() }] }
})

let detailRequest = 0
watch(selectedJobId, async (jobId) => {
  const request = ++detailRequest
  selectedJob.value = null
  descriptionExpanded.value = false
  if (!jobId) return
  detailLoading.value = true
  try {
    const job = await jobDataSource.getJob(jobId)
    if (request === detailRequest) {
      selectedJob.value = job
      if (auth.isAuthenticated && job && !isViewed(jobId)) {
        await jobDataSource.markJobViewed(jobId)
        markJobViewedLocally(jobId)
      }
    }
  } finally {
    if (request === detailRequest) detailLoading.value = false
  }
})

function timestamp(job: DashboardJobSummary): number { return Date.parse(job.postedAt ?? job.firstSeenAt) || 0 }
function formatDescription(value: string): DescriptionBlock[] {
  const lines = value
    .replace(/\r\n?/g, '\n')
    .replace(/\\r\\n|\\n|\\r/g, '\n')
    .replace(/\\([\\`*_[\]{}()#+.!|>&-])/g, '$1')
    .split('\n')
    .map((line) => line.trim())

  const blocks: DescriptionBlock[] = []
  let listItems: string[] = []
  const flushList = (): void => {
    if (listItems.length) blocks.push({ type: 'list', items: listItems })
    listItems = []
  }

  for (const line of lines) {
    if (!line) {
      flushList()
      continue
    }

    const bullet = line.match(/^(?:[-*•]|\d+[.)])\s+(.+)$/)
    if (bullet) {
      listItems.push(cleanInlineMarkdown(bullet[1]))
      continue
    }

    flushList()
    const markdownHeading = line.match(/^#{1,4}\s+(.+)$/)
    const boldHeading = line.match(/^\*\*(.+?)\*\*:?$/)
    if (markdownHeading || boldHeading || isPlainTextHeading(line)) {
      blocks.push({ type: 'heading', text: cleanInlineMarkdown(markdownHeading?.[1] ?? boldHeading?.[1] ?? line) })
    } else {
      blocks.push({ type: 'paragraph', text: cleanInlineMarkdown(line) })
    }
  }
  flushList()
  return blocks
}

function cleanInlineMarkdown(value: string): string {
  return value.replace(/^\*+|\*+$/g, '').replace(/\s+/g, ' ').trim()
}

function isPlainTextHeading(value: string): boolean {
  const normalized = value.replace(/:$/, '').trim()
  if (normalized.length > 64 || /[.!?]$/.test(normalized)) return false
  if (value.endsWith(':')) return true
  return /^(?:about (?:us|the role|you)|additional information|ai usage disclosure|benefits|compensation|education|examples of the problems you'll solve|job requirements|nice to have|one last thing|our commitment|qualifications|responsibilities|salary range|the opportunity|training & onboarding|what (?:the role offers|success looks like|we're looking for|you(?:'ll| will)? do|you need to succeed)|who we are|your impact)$/i.test(normalized)
}
function initials(company: string): string { return company.split(/\s+/).slice(0, 2).map((word) => word[0]).join('').toUpperCase() }
function workplaceLabel(value: WorkplaceType): string { return ({ remote: 'Remote', hybrid: 'Hybrid', onsite: 'On-site', unknown: 'Workplace unknown' } satisfies Record<WorkplaceType, string>)[value] }
function sourceLabel(value: string): string { return ({ workday: 'Workday', indeed: 'Indeed', linkedin: 'LinkedIn', zip_recruiter: 'ZipRecruiter' } as Record<string, string>)[value] ?? value }
function statusLabel(value: JobUserStatus): string { return ({ new: 'New', saved: 'Saved', selected: 'Shortlist', applied: 'Applied', rejected: 'Rejected' } satisfies Record<JobUserStatus, string>)[value] }
// A score stays visible after a profile edit instead of vanishing. Hiding it
// used to be harmless because the next scheduled run recomputed it within a
// day; since that run only looks at jobs discovered in the last two days,
// hiding an older score would mean never showing one again. isStaleScore()
// marks what no longer reflects the current profile.
function assessmentFor(jobId: string): JobUserState | undefined {
  const assessment = stateFor(jobId)
  return assessment && assessment.coarseScore !== null ? assessment : undefined
}
function isStaleScore(jobId: string): boolean {
  const assessment = assessmentFor(jobId)
  return assessment !== undefined && assessment.profileVersion !== currentProfileVersion.value
}
function staleLabel(jobId: string): string {
  const version = assessmentFor(jobId)?.profileVersion
  return version === null || version === undefined ? 'older profile' : `profile v${version}`
}
function stateFor(jobId: string): JobUserState | undefined { return userState.value.jobs.find((job) => job.jobId === jobId) }
function reasoningEyebrow(jobId: string): string {
  if (!assessmentFor(jobId)?.coarseScoreReasoning) {
    return scoringAttemptFor(jobId)?.scoreError ? 'SCORING FAILED' : 'NOT SCORED FOR YOU YET'
  }
  return isStaleScore(jobId) ? `WHY THIS FIT — ${staleLabel(jobId).toUpperCase()}` : 'WHY THIS FITS YOU'
}
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
  if (nextStatus === 'applied' && selectedJob.value?.jobId === jobId) recordApplication(selectedJob.value)
}

async function blockCompany(company: string): Promise<void> {
  const previous = blockedCompanies.value
  blockedCompanies.value = new Set([...previous, normalizeCompany(company)])
  try {
    blockedCompanies.value = new Set(await jobDataSource.blockCompany(company))
    message.success(`${company} is blocked. Undo it under Settings.`)
  } catch (reason) {
    blockedCompanies.value = previous
    message.error(reason instanceof Error ? reason.message : `Unable to block ${company}.`)
  }
}

// Best-effort: a failure here must never block the job-status toggle above,
// since the application tracker is a separate service from job-discovery.
async function recordApplication(job: DashboardJob): Promise<void> {
  try {
    await applicationDataSource.createFromJob({
      jobId: job.jobId,
      sourceUrl: job.primaryListing?.sourceUrl ?? job.primaryListingUrl,
      applyUrl: job.primaryListing?.applyUrl ?? null,
      company: job.company,
      title: job.title,
      location: job.location,
      jdText: job.description,
    })
  } catch (error) {
    console.error('failed to record application', error)
  }
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
.eyebrow { color:#9ac4ff; font:750 11px/1.35 system-ui,sans-serif; letter-spacing:.105em; }
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
.row-main{min-width:0}.topline{display:flex;justify-content:space-between;gap:10px}.topline span{overflow:hidden;color:#aab3c1;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.topline small{color:#667184;font-size:10px}.job-row h2{overflow:hidden;margin:4px 0 7px;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.job-row p{margin:0;color:var(--muted);font-size:10px}.requirements{display:flex;align-items:center;gap:5px;overflow:hidden;margin-top:8px;white-space:nowrap}.requirements span{overflow:hidden;max-width:105px;padding:3px 6px;border:1px solid rgba(255,255,255,.07);border-radius:5px;color:#9da8b8;background:rgba(255,255,255,.035);font-size:9px;text-overflow:ellipsis}.requirements .years{flex:none;border-color:rgba(231,169,75,.2);color:#e7b35b;background:rgba(231,169,75,.08);font-weight:700}.requirements .new-grad{flex:none;border-color:rgba(62,207,142,.24);color:#53d99f;background:rgba(62,207,142,.1);font-weight:700}.requirements small{flex:none;color:#687487;font-size:9px}.job-row footer{display:flex;gap:7px;margin-top:10px}.job-row em{padding:3px 6px;border-radius:5px;font:700 9px monospace;text-transform:uppercase;font-style:normal}.is-new{color:#8bb8ff;background:rgba(74,125,207,.14)}.is-category{color:#c9a8f5;background:rgba(161,124,244,.12)}.is-eligible{color:#53d99f;background:rgba(62,207,142,.1)}.is-review{color:#edb85f;background:rgba(231,169,75,.1)}.is-excluded{color:#e47784;background:rgba(224,88,103,.1)}.user-status{color:#a58af3;background:rgba(161,124,244,.12)}.lifecycle-stale{color:#edb85f;background:rgba(231,169,75,.1)}.lifecycle-archived{color:#8993a3;background:rgba(137,147,163,.1)}
.side-col{display:flex;flex-direction:column;align-items:flex-end;gap:8px}
.quick-actions{display:flex;gap:5px}.quick-actions a,.quick-actions button{display:grid;place-items:center;width:23px;height:23px;border:1px solid var(--border);border-radius:6px;color:var(--muted);background:rgba(255,255,255,.03);font-size:12px;line-height:1;text-decoration:none;cursor:pointer}.quick-actions a:hover,.quick-actions button:hover{color:#edf1f7;background:#1b202b}.quick-actions button.active{color:#e47784;border-color:rgba(224,88,103,.35);background:rgba(224,88,103,.1)}
.score{display:flex;flex-direction:column;align-items:flex-end;min-width:39px}.score b{font-size:19px}.score small{color:#606a7b;font-size:8px}.score-strong{color:#4bd49d}.score-medium{color:#e9b65e}.score-low{color:#e87783}.score-empty{color:#5f6979}
.score.stale,.detail-score.stale{opacity:.5}.detail-score.stale small{color:#8a8172;text-transform:none}
.detail{padding:23px 25px 30px}.detail>header{display:flex;justify-content:space-between;gap:20px}.detail>header span{color:#8eb8f6;font-size:12px}.detail h2{margin:5px 0 7px;font-size:23px}.detail header p{margin:0;color:var(--muted);font-size:12px}.detail-score{display:flex;flex:none;flex-direction:column;align-items:center;justify-content:center;width:69px;height:61px;border:1px solid currentColor;border-radius:10px}.detail-score b{font-size:24px}.detail-score small{color:#707b8d;font-size:8px;text-transform:uppercase}.actions{display:flex;gap:8px;margin:20px 0;padding-bottom:20px;border-bottom:1px solid var(--border)}.generate{margin-left:auto}
.reasoning{margin-bottom:25px;padding:17px 18px;border:1px solid rgba(112,167,248,.24);border-radius:10px;background:#151a22}.reasoning.pending{border-color:rgba(231,169,75,.28);background:#1a1917}.reasoning.pending .eyebrow{color:#efc574}.reasoning p{margin:9px 0 10px;color:#d0d6df;font-size:13px;line-height:1.65}.reasoning small{color:#8a96a8;font:10px/1.4 ui-monospace,monospace}
.job-requirements{margin-bottom:25px}.requirement-tags{display:flex;flex-wrap:wrap;gap:8px;margin-top:11px}.requirement-tags span{padding:6px 9px;border:1px solid rgba(255,255,255,.11);border-radius:6px;color:#c2cad6;background:#171c24;font-size:11px;line-height:1.35}.requirement-tags .requirement-years{border-color:rgba(231,169,75,.32);color:#f0c16f;background:rgba(231,169,75,.1);font-weight:700}.requirement-tags .requirement-new-grad{border-color:rgba(62,207,142,.32);color:#67e2ae;background:rgba(62,207,142,.11);font-weight:700}
.description-section{border:1px solid rgba(255,255,255,.1);border-radius:10px;background:#10141b}.description-heading{display:flex;align-items:center;gap:14px;padding:14px 16px}.description-toggle{display:flex;flex:1;align-items:center;justify-content:space-between;min-width:0;padding:0;border:0;border-radius:5px;color:inherit;background:transparent;text-align:left;cursor:pointer}.description-toggle:focus-visible{outline:2px solid #79aef7;outline-offset:5px}.description-title{display:flex;flex-direction:column;gap:5px}.description-title small{color:#929daf;font-size:11px}.description-toggle-label{display:flex;align-items:center;gap:7px;color:#a9caff;font-size:12px;font-weight:650}.description-toggle-label i{display:inline-block;color:#7e8da2;font-size:16px;font-style:normal;transition:transform .18s ease}.description-toggle[aria-expanded="true"] .description-toggle-label i{transform:rotate(180deg)}.description-heading>a{flex:none;color:#91bcff;font-size:11px;text-decoration:none}.description-heading>a:hover{color:#c1daff}.description{padding:8px 22px 24px;border-top:1px solid rgba(255,255,255,.08);color:#cbd3df;background:#0c1016;font-size:13px;line-height:1.75}.description h3{margin:24px 0 9px;padding-left:10px;border-left:3px solid #6fa8ff;color:#f0f4fa;font-size:15px;font-weight:720;line-height:1.4;letter-spacing:-.01em}.description h3:first-child{margin-top:16px}.description p{margin:0 0 12px}.description ul{display:grid;gap:7px;margin:8px 0 18px;padding-left:21px}.description li{padding-left:3px}.description li::marker{color:#77adf9}.description-empty{margin:16px 0!important;color:#929daf}
.sources{margin-top:23px}.sources>a{display:grid;grid-template-columns:100px 1fr auto;gap:12px;margin-top:8px;padding:10px 12px;border:1px solid var(--border);border-radius:7px;color:#b6bfcc;text-decoration:none}.sources a small{color:#6f7989}.sources a span{color:#78aaf3}
.empty,.loading{display:grid;place-items:center;max-width:1500px;height:420px;margin:auto;border:1px solid var(--border);border-radius:11px;background:rgba(18,21,28,.8)}
.load-error{max-width:1500px;margin:16px auto}
@media(max-width:1050px){.jobs-page{padding:24px 18px}.filters{grid-template-columns:repeat(2,1fr)}.search{grid-column:1/-1}.workspace{grid-template-columns:1fr;height:auto}.job-list{max-height:540px}}
@media(max-width:640px){.hero{align-items:flex-start;flex-direction:column}.snapshot{width:100%;box-sizing:border-box}.filters{grid-template-columns:1fr 1fr}.actions{flex-wrap:wrap}.generate{width:100%;margin-left:0}.score{display:none}.description-heading{align-items:flex-start;flex-direction:column}.description{padding:6px 16px 20px}}
</style>
