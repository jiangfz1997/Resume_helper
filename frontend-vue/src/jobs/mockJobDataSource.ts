import listingsCsv from '../mocks/job-listings.csv?raw'
import recordsCsv from '../mocks/job-records.csv?raw'
import { classifyJobCategory } from './category'
import { normalizeCompany } from './company'
import { cleanExportedString, nullableString, parseCsv } from './csv'
import type {
  DashboardBootstrap,
  DashboardJob,
  DashboardJobSummary,
  DashboardRunSummary,
  DashboardUserState,
  DiscoverySettings,
  DiscoveryCrawler,
  EligibilityStatus,
  JobDataSource,
  JobListing,
  JobRecord,
  JobUserStatus,
  ManualCrawlerResult,
  ManualScoringResult,
  ScoringProfileSettings,
  ScoringQueueSummary,
  WorkplaceType,
} from './models'

function parseFilterCodes(value: string): string[] {
  try {
    const parsed: unknown = JSON.parse(cleanExportedString(value) || '[]')
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

function parseScore(value: string): number | null {
  if (!value.trim()) return null
  const score = Number(value)
  return Number.isFinite(score) ? score : null
}

function parseKeywords(value: string): string[] {
  try {
    const parsed: unknown = JSON.parse(cleanExportedString(value) || '[]')
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

function toRecord(row: Record<string, string>): JobRecord {
  return {
    jobId: row.job_id,
    company: cleanExportedString(row.canonical_company) || 'Unknown company',
    location: cleanExportedString(row.canonical_location) || 'Location unavailable',
    title: cleanExportedString(row.canonical_title) || 'Untitled role',
    description: cleanExportedString(row.description),
    descriptionChars: Number(row.description_chars) || 0,
    jobCategory: classifyJobCategory(cleanExportedString(row.canonical_title) || ''),
    eligibilityStatus: (row.eligibility_status || 'review') as EligibilityStatus,
    filterCodes: parseFilterCodes(row.filter_codes),
    workplaceType: (row.workplace_type || 'unknown') as WorkplaceType,
    coarseScore: parseScore(row.coarse_score),
    requiredYearsMin: parseScore(row.required_years_min ?? ''),
    requiredYearsMax: parseScore(row.required_years_max ?? ''),
    isNewGrad: row.is_new_grad === 'true',
    newGradSignals: parseKeywords(row.new_grad_signals ?? ''),
    requirementKeywords: parseKeywords(row.requirement_keywords ?? ''),
    coarseScoreReasoning: nullableString(row.coarse_score_reasoning),
    scoreModel: nullableString(row.score_model),
    scoredAt: nullableString(row.scored_at),
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }
}

function toListing(row: Record<string, string>): JobListing {
  return {
    listingId: row.listing_id,
    jobId: row.job_id,
    source: row.source,
    sourceUrl: row.source_url,
    applyUrl: row.apply_url_canonical,
    postedAt: nullableString(row.posted_at),
    postedAtRaw: nullableString(row.posted_at_raw),
    postedAtQuality: row.posted_at_quality,
    firstSeenAt: row.first_seen_at,
    lastSeenAt: row.last_seen_at,
    status: row.status,
  }
}

function selectPrimaryListing(listings: JobListing[]): JobListing | null {
  return [...listings].sort((left, right) => {
    const activeDifference = Number(right.status === 'active') - Number(left.status === 'active')
    if (activeDifference !== 0) return activeDifference
    return Date.parse(right.lastSeenAt) - Date.parse(left.lastSeenAt)
  })[0] ?? null
}

export class MockJobDataSource implements JobDataSource {
  private readonly jobs: DashboardJob[]

  constructor() {
    const listings = parseCsv(listingsCsv).map(toListing)
    const listingsByJob = new Map<string, JobListing[]>()

    for (const listing of listings) {
      const existing = listingsByJob.get(listing.jobId) ?? []
      existing.push(listing)
      listingsByJob.set(listing.jobId, existing)
    }

    this.jobs = parseCsv(recordsCsv).map(toRecord).map((record) => {
      const jobListings = listingsByJob.get(record.jobId) ?? []
      const primaryListing = selectPrimaryListing(jobListings)
      const seenDates = jobListings.map((listing) => listing.lastSeenAt).sort()
      const lastSeenAt = seenDates[seenDates.length - 1] ?? record.updatedAt
      return {
        ...record,
        firstDiscoveredRunId: legacyRunId(record.createdAt),
        postedAt: primaryListing?.postedAt ?? null,
        firstSeenAt: jobListings.map((listing) => listing.firstSeenAt).sort()[0] ?? record.createdAt,
        sources: [...new Set(jobListings.map((listing) => listing.source))].sort(),
        primaryListingUrl: primaryListing?.applyUrl || primaryListing?.sourceUrl || null,
        lastSeenAt,
        lifecycleStatus: lifecycleStatus(lastSeenAt),
        listings: jobListings,
        primaryListing,
      }
    })
  }

  async getBootstrap(): Promise<DashboardBootstrap> {
    const [jobs, runs, userState, scoringProfile, scoringQueue, blockedCompanies] = await Promise.all([
      this.listJobs(), this.listRuns(), this.getUserState(), this.getScoringProfile(), this.getScoringQueue(),
      this.listBlockedCompanies(),
    ])
    return { jobs, runs, userState, scoringProfile, scoringQueue, blockedCompanies }
  }

  async listJobs(): Promise<DashboardJobSummary[]> {
    const blocked = new Set(await this.listBlockedCompanies())
    return this.jobs.filter((job) => !blocked.has(normalizeCompany(job.company)))
  }

  async getJob(jobId: string): Promise<DashboardJob | null> {
    return this.jobs.find((job) => job.jobId === jobId) ?? null
  }

  async listRuns(): Promise<DashboardRunSummary[]> {
    const grouped = new Map<string, DashboardJob[]>()
    for (const job of this.jobs) grouped.set(job.firstDiscoveredRunId, [...(grouped.get(job.firstDiscoveredRunId) ?? []), job])
    return [...grouped.entries()].map(([runId, jobs]) => ({
      runId,
      discoveredAt: jobs.map((job) => job.createdAt).sort()[0],
      newJobsCount: jobs.length,
      observedCount: jobs.length,
      eligibleCount: jobs.filter((job) => job.eligibilityStatus === 'eligible').length,
      reviewCount: jobs.filter((job) => job.eligibilityStatus === 'review').length,
      excludedCount: jobs.filter((job) => job.eligibilityStatus === 'excluded').length,
      errorCount: 0,
      sources: [...new Set(jobs.flatMap((job) => job.sources))],
      status: 'unknown',
    })).sort((left, right) => Date.parse(right.discoveredAt) - Date.parse(left.discoveredAt))
  }

  async getScoringQueue(): Promise<ScoringQueueSummary> {
    return {
      eligibleTotal: this.jobs.filter((job) => job.eligibilityStatus === 'eligible').length,
      scoredCurrent: this.jobs.filter((job) => job.coarseScore !== null).length,
      pending: this.jobs.filter((job) => job.eligibilityStatus === 'eligible' && job.coarseScore === null).length,
      queued: 0,
      failed: 0,
      archivedSkipped: 0,
    }
  }

  async scoreJob(jobId: string): Promise<void> {
    void jobId
  }

  async scoreRun(runId: string, limit: number): Promise<ManualScoringResult> {
    const state = loadMockState()
    const profile = await this.getScoringProfile()
    const currentScores = new Set(state.jobs.filter((job) => (
      job.coarseScore !== null && job.profileVersion === profile.profileVersion
    ) || (
      job.scoringStatus === 'queued' && job.scoringProfileVersion === profile.profileVersion
    )).map((job) => job.jobId))
    const eligible = this.jobs.filter((job) => job.firstDiscoveredRunId === runId && job.eligibilityStatus === 'eligible')
    const remaining = eligible.filter((job) => !currentScores.has(job.jobId))
    return { runId, eligible: eligible.length, remaining: remaining.length, queued: Math.min(limit, remaining.length) }
  }

  async runCrawler(crawler: DiscoveryCrawler): Promise<ManualCrawlerResult> {
    return {
      runId: `manual-${new Date().toISOString()}`,
      crawlers: crawler === 'all' ? ['workday', 'jobspy', 'simplify'] : crawler === 'both' ? ['workday', 'jobspy'] : [crawler],
    }
  }

  async getUserState(): Promise<DashboardUserState> {
    return loadMockState()
  }

  async markJobViewed(jobId: string): Promise<void> {
    const state = loadMockState()
    const now = new Date().toISOString()
    const existing = state.jobs.find((job) => job.jobId === jobId)
    state.jobs = [...state.jobs.filter((job) => job.jobId !== jobId), {
      jobId,
      status: existing?.status ?? 'new',
      firstViewedAt: existing?.firstViewedAt ?? now,
      lastViewedAt: now,
      updatedAt: now,
      coarseScore: existing?.coarseScore ?? null,
      coarseScoreReasoning: existing?.coarseScoreReasoning ?? null,
      scoreModel: existing?.scoreModel ?? null,
      scoreVersion: existing?.scoreVersion ?? null,
      profileVersion: existing?.profileVersion ?? null,
      scoredAt: existing?.scoredAt ?? null,
      scoringStatus: existing?.scoringStatus ?? null,
      scoringProfileVersion: existing?.scoringProfileVersion ?? null,
      scoreError: existing?.scoreError ?? null,
    }]
    saveMockState(state)
  }

  async setJobStatus(jobId: string, status: JobUserStatus): Promise<void> {
    await this.markJobViewed(jobId)
    const state = loadMockState()
    const now = new Date().toISOString()
    state.jobs = state.jobs.map((job) => job.jobId === jobId ? { ...job, status, updatedAt: now } : job)
    saveMockState(state)
  }

  async markRunViewed(runId: string): Promise<void> {
    const state = loadMockState()
    state.runs = [...state.runs.filter((run) => run.runId !== runId), { runId, viewedAt: new Date().toISOString() }]
    saveMockState(state)
  }

  async listBlockedCompanies(): Promise<string[]> {
    return loadSetting<string[]>(MOCK_BLOCKLIST_KEY, [])
  }

  async blockCompany(company: string): Promise<string[]> {
    const blocked = new Set(await this.listBlockedCompanies())
    blocked.add(normalizeCompany(company))
    return saveBlocklist(blocked)
  }

  async unblockCompany(company: string): Promise<string[]> {
    const blocked = new Set(await this.listBlockedCompanies())
    blocked.delete(normalizeCompany(company))
    return saveBlocklist(blocked)
  }

  async getScoringProfile(): Promise<ScoringProfileSettings> {
    return loadSetting(MOCK_PROFILE_KEY, emptyMockProfile())
  }

  async saveScoringProfile(profile: ScoringProfileSettings): Promise<ScoringProfileSettings> {
    const saved = { ...profile, profileVersion: (profile.profileVersion ?? 0) + 1, updatedAt: new Date().toISOString() }
    localStorage.setItem(MOCK_PROFILE_KEY, JSON.stringify(saved))
    return saved
  }

  async getDiscoverySettings(): Promise<DiscoverySettings> {
    return loadSetting(MOCK_DISCOVERY_KEY, defaultMockDiscovery())
  }

  async saveDiscoverySettings(settings: DiscoverySettings): Promise<DiscoverySettings> {
    const saved = { ...settings, configVersion: (settings.configVersion ?? 0) + 1, updatedAt: new Date().toISOString() }
    localStorage.setItem(MOCK_DISCOVERY_KEY, JSON.stringify(saved))
    return saved
  }
}

const MOCK_STATE_KEY = 'job-dashboard:user-state:v2'
const MOCK_PROFILE_KEY = 'job-dashboard:scoring-profile:v1'
const MOCK_DISCOVERY_KEY = 'job-dashboard:discovery-settings:v1'
const MOCK_BLOCKLIST_KEY = 'job-dashboard:blocked-companies:v1'

function saveBlocklist(companies: Set<string>): string[] {
  const sorted = [...companies].sort()
  localStorage.setItem(MOCK_BLOCKLIST_KEY, JSON.stringify(sorted))
  return sorted
}

function legacyRunId(createdAt: string): string {
  const date = new Date(createdAt)
  date.setUTCMinutes(0, 0, 0)
  return `legacy-${date.toISOString().replace('.000Z', 'Z')}`
}

function lifecycleStatus(lastSeenAt: string): 'active' | 'stale' | 'archived' {
  const ageDays = (Date.now() - Date.parse(lastSeenAt)) / 86_400_000
  return ageDays >= 30 ? 'archived' : ageDays >= 7 ? 'stale' : 'active'
}

function loadMockState(): DashboardUserState {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(MOCK_STATE_KEY) ?? '{}')
    if (parsed && typeof parsed === 'object' && 'jobs' in parsed && 'runs' in parsed) {
      const state = parsed as DashboardUserState
      return {
        ...state,
        jobs: state.jobs.map((job) => ({
          ...job,
          coarseScore: job.coarseScore ?? null,
          coarseScoreReasoning: job.coarseScoreReasoning ?? null,
          scoreModel: job.scoreModel ?? null,
          scoreVersion: job.scoreVersion ?? null,
          profileVersion: job.profileVersion ?? null,
          scoredAt: job.scoredAt ?? null,
          scoringStatus: job.scoringStatus ?? null,
          scoringProfileVersion: job.scoringProfileVersion ?? null,
          scoreError: job.scoreError ?? null,
        })),
      }
    }
  } catch {
    // Ignore invalid local development state.
  }
  return { jobs: [], runs: [] }
}

function saveMockState(state: DashboardUserState): void {
  localStorage.setItem(MOCK_STATE_KEY, JSON.stringify(state))
}

function loadSetting<T>(key: string, fallback: T): T {
  try {
    return JSON.parse(localStorage.getItem(key) ?? '') as T
  } catch {
    return fallback
  }
}

function emptyMockProfile(): ScoringProfileSettings {
  return { skills: [], targetTitles: [], minYearsExperience: null, locationPreference: '', prefersNewGrad: false, active: true, profileVersion: null, updatedAt: null }
}

function defaultMockDiscovery(): DiscoverySettings {
  return {
    searchTerms: ['Software Engineer', 'SDET', 'QA Engineer'], jobspyLocation: 'Canada', hoursOld: 24,
    jobspyMaxResults: 15, workdayMaxResults: 10, sites: ['indeed', 'linkedin'], acceptedLocations: [],
    includeTitleKeywords: ['software engineer', 'software developer', 'backend', 'frontend', 'full stack', 'developer', 'sde', 'swe', 'qa engineer', 'quality assurance', 'qa analyst', 'sdet', 'test engineer', 'test automation', 'automation engineer'],
    excludeTitleKeywords: ['staff', 'principal', 'director', 'vp', 'vice president', 'head of'],
    reviewTitleKeywords: ['senior', 'sr.', 'lead'], minDescriptionChars: 300, maxRequiredYears: null,
    configVersion: null, updatedAt: null,
  }
}
