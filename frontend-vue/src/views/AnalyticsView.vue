<template>
  <main class="analytics-page">
    <header class="page-heading">
      <div>
        <span class="eyebrow">JOB MARKET SIGNALS</span>
        <h1>Tech stack frequency</h1>
        <p>How often each technology appears across discovered and applied jobs.</p>
      </div>
      <n-button :loading="loading" secondary @click="load">Refresh</n-button>
    </header>

    <n-alert v-if="loadError" type="error" closable @close="loadError = ''">{{ loadError }}</n-alert>
    <n-alert v-if="loadWarning" type="warning" closable @close="loadWarning = ''">{{ loadWarning }}</n-alert>

    <section class="filters" aria-label="Analytics filters">
      <n-radio-group v-model:value="scope" class="scope-tabs">
        <n-radio-button value="market">Discovered jobs</n-radio-button>
        <n-radio-button value="applied">Applied jobs</n-radio-button>
        <n-radio-button value="compare">Compare</n-radio-button>
      </n-radio-group>
      <div class="filter-selects">
        <n-select v-model:value="days" :options="dateOptions" aria-label="Date range" />
        <n-select v-model:value="category" :options="categoryOptions" aria-label="Job category" />
        <n-select
          v-if="scope !== 'applied'"
          v-model:value="eligibility"
          :options="eligibilityOptions"
          aria-label="Eligibility"
        />
      </div>
    </section>

    <section class="summary-grid" aria-label="Sample summary">
      <article class="summary-card">
        <span class="summary-label">Discovered sample</span>
        <strong>{{ marketDocuments.length }}</strong>
        <small>{{ marketCandidates.length }} jobs match the filters</small>
      </article>
      <article class="summary-card">
        <span class="summary-label">Applied sample</span>
        <strong>{{ appliedDocuments.length }}</strong>
        <small>{{ appliedCandidates.length }} applications match the filters</small>
      </article>
      <article class="summary-card">
        <span class="summary-label">Keyword coverage</span>
        <strong>{{ activeCoverage }}%</strong>
        <small>{{ activeCoverageLabel }}</small>
      </article>
      <article class="summary-card accent-card">
        <span class="summary-label">Most frequent</span>
        <strong>{{ leadingSkill?.name ?? '—' }}</strong>
        <small v-if="leadingSkill">{{ leadingSkillCaption }}</small>
        <small v-else>No recognized keywords yet</small>
      </article>
    </section>

    <section class="analytics-grid">
      <article class="chart-card">
        <div class="section-heading">
          <div>
            <span class="eyebrow">TOP TECHNOLOGIES</span>
            <h2>{{ chartTitle }}</h2>
          </div>
          <span class="method-note">One mention max per job</span>
        </div>

        <div v-if="loading" class="loading"><n-spin size="large" /></div>
        <n-empty v-else-if="!chartRows.length" description="No extracted technology keywords for this sample" />

        <div v-else-if="scope !== 'compare'" class="bars">
          <button
            v-for="row in singleRows"
            :key="row.name"
            type="button"
            class="bar-row"
            :class="{ selected: selectedKeyword === row.name }"
            @click="selectedKeyword = row.name"
          >
            <span class="keyword-name">{{ row.name }}</span>
            <span class="bar-track"><i :style="{ width: `${row.rate}%` }" /></span>
            <span class="bar-value"><b>{{ row.rate }}%</b><small>{{ row.count }} jobs</small></span>
          </button>
        </div>

        <div v-else class="bars compare-bars">
          <button
            v-for="row in compareRows"
            :key="row.name"
            type="button"
            class="compare-row"
            :class="{ selected: selectedKeyword === row.name }"
            @click="selectedKeyword = row.name"
          >
            <span class="keyword-name">{{ row.name }}</span>
            <span class="comparison">
              <span class="comparison-line">
                <small>Market</small><span class="bar-track"><i :style="{ width: `${row.marketRate}%` }" /></span><b>{{ row.marketRate }}%</b>
              </span>
              <span class="comparison-line applied-line">
                <small>Applied</small><span class="bar-track"><i :style="{ width: `${row.appliedRate}%` }" /></span><b>{{ row.appliedRate }}%</b>
              </span>
            </span>
          </button>
        </div>

        <footer class="legend">
          <span v-if="scope === 'compare'"><i class="market-dot" /> Market</span>
          <span v-if="scope === 'compare'"><i class="applied-dot" /> Applied</span>
          <span>Rate = jobs containing keyword ÷ analyzed jobs</span>
        </footer>
      </article>

      <aside class="detail-card">
        <div class="section-heading">
          <div>
            <span class="eyebrow">MATCHING JOBS</span>
            <h2>{{ selectedKeyword || 'Select a keyword' }}</h2>
          </div>
          <n-tag v-if="selectedKeyword" round>{{ matchingDocuments.length }}</n-tag>
        </div>

        <p v-if="!selectedKeyword" class="detail-placeholder">Click a bar to see which jobs contributed to that frequency.</p>
        <n-empty v-else-if="!matchingDocuments.length" description="No matching jobs" />
        <ol v-else class="job-list">
          <li v-for="document in matchingDocuments.slice(0, 12)" :key="`${document.source}-${document.id}`">
            <div>
              <strong>{{ document.title }}</strong>
              <span>{{ document.company }}</span>
            </div>
            <n-tag :type="document.source === 'applied' ? 'success' : 'info'" size="small" round>
              {{ document.source === 'applied' ? 'Applied' : 'Market' }}
            </n-tag>
          </li>
        </ol>
        <small v-if="matchingDocuments.length > 12" class="more-jobs">+{{ matchingDocuments.length - 12 }} more jobs</small>
      </aside>
    </section>

    <n-alert v-if="marketCandidates.length > marketDocuments.length && scope !== 'applied'" type="info" class="coverage-note">
      {{ marketCandidates.length - marketDocuments.length }} discovered jobs are excluded from the denominator because their list records do not yet contain extracted keywords. This keeps missing data from lowering every percentage.
    </n-alert>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { aggregateSkills, extractSkills, isWithinDays, normalizeSkills } from '../analytics/skills'
import type { SkillDocument, SkillStat } from '../analytics/skills'
import { applicationDataSource } from '../applications/dataSource'
import type { JobApplication } from '../applications/models'
import { classifyJobCategory } from '../jobs/category'
import { jobDataSource } from '../jobs/dataSource'
import type { DashboardJob, DashboardJobSummary, JobCategory } from '../jobs/models'

type Scope = 'market' | 'applied' | 'compare'
type CategoryFilter = 'all' | JobCategory
type EligibilityFilter = 'actionable' | 'eligible' | 'all'
type DaysFilter = 7 | 30 | 90 | 'all'
type MarketJobWithOptionalDescription = DashboardJobSummary & Partial<Pick<DashboardJob, 'description'>>

interface CompareRow {
  name: string
  marketRate: number
  appliedRate: number
  marketCount: number
  appliedCount: number
}

const jobs = ref<DashboardJobSummary[]>([])
const applications = ref<JobApplication[]>([])
const loading = ref(true)
const loadError = ref('')
const loadWarning = ref('')
const scope = ref<Scope>('market')
const days = ref<DaysFilter>(30)
const category = ref<CategoryFilter>('all')
const eligibility = ref<EligibilityFilter>('actionable')
const selectedKeyword = ref<string | null>(null)

const dateOptions = [
  { label: 'Last 7 days', value: 7 },
  { label: 'Last 30 days', value: 30 },
  { label: 'Last 90 days', value: 90 },
  { label: 'All time', value: 'all' },
]
const categoryOptions = [
  { label: 'All job tracks', value: 'all' },
  { label: 'Software engineering', value: 'sde' },
  { label: 'QA / test automation', value: 'qa' },
]
const eligibilityOptions = [
  { label: 'Actionable roles', value: 'actionable' },
  { label: 'Eligible only', value: 'eligible' },
  { label: 'All decisions', value: 'all' },
]

const marketCandidates = computed(() => jobs.value.filter((job) => {
  if (!isWithinDays(job.postedAt ?? job.firstSeenAt, days.value === 'all' ? null : days.value)) return false
  if (category.value !== 'all' && job.jobCategory !== category.value) return false
  if (eligibility.value === 'actionable' && job.eligibilityStatus === 'excluded') return false
  if (eligibility.value === 'eligible' && job.eligibilityStatus !== 'eligible') return false
  return true
}))

const appliedCandidates = computed(() => applications.value.filter((application) => {
  if (!isWithinDays(application.appliedAt, days.value === 'all' ? null : days.value)) return false
  if (category.value !== 'all' && classifyJobCategory(application.title) !== category.value) return false
  return true
}))

const marketDocuments = computed<SkillDocument[]>(() => marketCandidates.value.flatMap((job) => {
  const localDescription = (job as MarketJobWithOptionalDescription).description?.trim() ?? ''
  const keywords = localDescription
    ? extractSkills(localDescription)
    : normalizeSkills(job.requirementKeywords)
  const hasAnalysis = Boolean(localDescription) || job.requirementKeywords.length > 0
  if (!hasAnalysis) return []
  return [{
    id: job.jobId,
    title: job.title,
    company: job.company,
    date: job.postedAt ?? job.firstSeenAt,
    source: 'market' as const,
    keywords,
  }]
}))

const appliedDocuments = computed<SkillDocument[]>(() => appliedCandidates.value.flatMap((application) => {
  if (!application.jdText.trim()) return []
  return [{
    id: application.applicationId,
    title: application.title,
    company: application.company,
    date: application.appliedAt,
    source: 'applied' as const,
    keywords: extractSkills(application.jdText),
  }]
}))

const marketStats = computed(() => aggregateSkills(marketDocuments.value))
const appliedStats = computed(() => aggregateSkills(appliedDocuments.value))
const singleRows = computed(() => (scope.value === 'applied' ? appliedStats.value : marketStats.value).slice(0, 20))
const compareRows = computed<CompareRow[]>(() => {
  const marketByName = new Map(marketStats.value.map((stat) => [stat.name, stat]))
  const appliedByName = new Map(appliedStats.value.map((stat) => [stat.name, stat]))
  return [...new Set([...marketByName.keys(), ...appliedByName.keys()])]
    .map((name) => ({
      name,
      marketRate: marketByName.get(name)?.rate ?? 0,
      appliedRate: appliedByName.get(name)?.rate ?? 0,
      marketCount: marketByName.get(name)?.count ?? 0,
      appliedCount: appliedByName.get(name)?.count ?? 0,
    }))
    .sort((left, right) => Math.max(right.marketRate, right.appliedRate) - Math.max(left.marketRate, left.appliedRate) || left.name.localeCompare(right.name))
    .slice(0, 20)
})
const chartRows = computed(() => scope.value === 'compare' ? compareRows.value : singleRows.value)

const leadingSkill = computed<SkillStat | null>(() => {
  if (scope.value === 'compare') {
    const first = compareRows.value[0]
    if (!first) return null
    return { name: first.name, count: Math.max(first.marketCount, first.appliedCount), rate: Math.max(first.marketRate, first.appliedRate) }
  }
  return singleRows.value[0] ?? null
})

const activeDocuments = computed(() => {
  if (scope.value === 'market') return marketDocuments.value
  if (scope.value === 'applied') return appliedDocuments.value
  return [...marketDocuments.value, ...appliedDocuments.value]
})
const matchingDocuments = computed(() => selectedKeyword.value
  ? activeDocuments.value.filter((document) => document.keywords.includes(selectedKeyword.value as string))
  : [])

const activeCoverage = computed(() => {
  const numerator = scope.value === 'market'
    ? marketDocuments.value.length
    : scope.value === 'applied'
      ? appliedDocuments.value.length
      : marketDocuments.value.length + appliedDocuments.value.length
  const denominator = scope.value === 'market'
    ? marketCandidates.value.length
    : scope.value === 'applied'
      ? appliedCandidates.value.length
      : marketCandidates.value.length + appliedCandidates.value.length
  return denominator ? Math.round((numerator / denominator) * 100) : 0
})
const activeCoverageLabel = computed(() => scope.value === 'market'
  ? `${marketDocuments.value.length} of ${marketCandidates.value.length} jobs analyzed`
  : scope.value === 'applied'
    ? `${appliedDocuments.value.length} of ${appliedCandidates.value.length} applications have a JD`
    : `${marketDocuments.value.length + appliedDocuments.value.length} of ${marketCandidates.value.length + appliedCandidates.value.length} records analyzed`)
const chartTitle = computed(() => scope.value === 'market'
  ? 'Discovered job requirements'
  : scope.value === 'applied'
    ? 'Your application mix'
    : 'Market vs. your applications')
const leadingSkillCaption = computed(() => scope.value === 'compare'
  ? `${leadingSkill.value?.rate ?? 0}% in the stronger of the two samples`
  : `${leadingSkill.value?.rate ?? 0}% of the active sample`)

watch([scope, days, category, eligibility], () => {
  selectedKeyword.value = null
})

onMounted(load)

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  loadWarning.value = ''
  const [jobResult, applicationResult] = await Promise.allSettled([
    jobDataSource.getBootstrap(),
    applicationDataSource.listApplications(),
  ])
  if (jobResult.status === 'fulfilled') jobs.value = jobResult.value.jobs
  if (applicationResult.status === 'fulfilled') applications.value = applicationResult.value

  const failures = [jobResult, applicationResult].filter((result) => result.status === 'rejected')
  if (failures.length === 2) {
    loadError.value = 'Unable to load job or application analytics.'
  } else if (failures.length === 1) {
    loadWarning.value = jobResult.status === 'rejected'
      ? 'Discovered jobs could not be loaded; application analytics are still available.'
      : 'Applications could not be loaded; discovered-job analytics are still available.'
  }
  loading.value = false
}
</script>

<style scoped>
.analytics-page {
  padding: 28px 32px 48px;
  min-height: calc(100vh - 56px);
  background:
    radial-gradient(circle at 82% -10%, rgba(74, 144, 226, 0.12), transparent 32rem),
    #101014;
}
.page-heading, .section-heading, .filters, .filter-selects, .summary-grid, .analytics-grid,
.comparison-line, .job-list li, .legend {
  display: flex;
}
.page-heading { align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 22px; }
h1, h2, p { margin: 0; }
h1 { margin-top: 4px; font-size: clamp(28px, 3vw, 40px); letter-spacing: -0.035em; }
h2 { margin-top: 4px; font-size: 18px; }
.page-heading p { margin-top: 8px; color: #94949d; }
.eyebrow { color: #6ea8e8; font: 700 11px/1.2 monospace; letter-spacing: 0.14em; }
.filters { align-items: center; justify-content: space-between; gap: 20px; margin: 18px 0; }
.scope-tabs { width: 480px; }
.filter-selects { gap: 10px; }
.filter-selects :deep(.n-select) { width: 190px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.summary-card, .chart-card, .detail-card {
  border: 1px solid rgba(255, 255, 255, 0.09);
  background: rgba(28, 28, 34, 0.88);
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.18);
}
.summary-card { min-height: 108px; padding: 17px 18px; border-radius: 12px; }
.summary-card strong { display: block; margin: 7px 0 2px; font-size: 28px; line-height: 1; }
.summary-label, .summary-card small { display: block; color: #92929c; }
.summary-label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
.summary-card small { margin-top: 7px; }
.accent-card { border-color: rgba(94, 169, 255, 0.3); background: linear-gradient(145deg, rgba(35, 69, 108, 0.62), rgba(28, 28, 34, 0.9)); }
.accent-card strong { color: #9bc9ff; }
.analytics-grid { display: grid; grid-template-columns: minmax(640px, 1.65fr) minmax(320px, 0.8fr); align-items: start; gap: 16px; }
.chart-card, .detail-card { padding: 22px; border-radius: 14px; }
.section-heading { align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.method-note { color: #73737d; font-size: 12px; }
.loading { display: grid; min-height: 320px; place-items: center; }
.bars { display: grid; gap: 5px; }
.bar-row, .compare-row {
  width: 100%; border: 0; border-radius: 8px; color: inherit; background: transparent; cursor: pointer; text-align: left;
}
.bar-row { display: grid; grid-template-columns: 128px minmax(180px, 1fr) 86px; align-items: center; gap: 12px; min-height: 38px; padding: 5px 8px; }
.bar-row:hover, .compare-row:hover, .bar-row.selected, .compare-row.selected { background: rgba(255, 255, 255, 0.055); }
.keyword-name { overflow: hidden; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { display: block; height: 9px; overflow: hidden; border-radius: 99px; background: rgba(255, 255, 255, 0.07); }
.bar-track i { display: block; height: 100%; min-width: 2px; border-radius: inherit; background: linear-gradient(90deg, #397dcc, #78b6ff); }
.bar-value { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; }
.bar-value b { color: #acd1fc; }
.bar-value small { color: #777781; }
.compare-row { display: grid; grid-template-columns: 128px minmax(260px, 1fr); align-items: center; gap: 12px; padding: 8px; }
.comparison { display: grid; gap: 5px; }
.comparison-line { display: grid; grid-template-columns: 50px minmax(160px, 1fr) 48px; align-items: center; gap: 8px; }
.comparison-line small { color: #85858e; }
.comparison-line b { color: #acd1fc; font-size: 12px; text-align: right; }
.applied-line .bar-track i { background: linear-gradient(90deg, #218b72, #57d5ae); }
.applied-line b { color: #7fe1c2; }
.legend { align-items: center; gap: 18px; margin-top: 18px; color: #777781; font-size: 12px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 8px; height: 8px; border-radius: 50%; }
.market-dot { background: #64a8f4; }
.applied-dot { background: #47c9a1; }
.detail-card { position: sticky; top: 20px; min-height: 340px; }
.detail-placeholder { color: #85858e; line-height: 1.6; }
.job-list { display: grid; gap: 0; margin: 0; padding: 0; list-style: none; }
.job-list li { align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.065); }
.job-list li:last-child { border-bottom: 0; }
.job-list div { min-width: 0; }
.job-list strong, .job-list span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-list span { margin-top: 3px; color: #85858e; font-size: 12px; }
.more-jobs { display: block; padding-top: 12px; color: #777781; }
.coverage-note { margin-top: 16px; }
@media (max-width: 1050px) {
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .analytics-grid { grid-template-columns: 1fr; }
  .detail-card { position: static; }
  .filters { align-items: stretch; flex-direction: column; }
  .scope-tabs { width: 100%; }
  .filter-selects :deep(.n-select) { flex: 1; width: auto; }
}
@media (max-width: 640px) {
  .analytics-page { padding: 20px 14px 36px; }
  .page-heading { align-items: stretch; flex-direction: column; }
  .summary-grid { grid-template-columns: 1fr; }
  .filter-selects { flex-direction: column; }
  .filter-selects :deep(.n-select) { width: 100%; }
  .chart-card, .detail-card { padding: 16px; }
  .bar-row { grid-template-columns: 92px minmax(90px, 1fr) 72px; gap: 8px; padding-inline: 4px; }
  .bar-value small { display: none; }
  .compare-row { grid-template-columns: 92px minmax(150px, 1fr); gap: 8px; padding-inline: 4px; }
  .comparison-line { grid-template-columns: 44px minmax(80px, 1fr) 42px; gap: 5px; }
  .legend { align-items: flex-start; flex-direction: column; gap: 6px; }
}
</style>
