import type {
  DashboardBootstrap,
  DashboardJob,
  DashboardJobSummary,
  DashboardRunSummary,
  DashboardUserState,
  DiscoverySettings,
  EligibilityStatus,
  JobCategory,
  JobDataSource,
  JobListing,
  ManualCrawlerResult,
  ManualScoringResult,
  JobUserStatus,
  ScoringProfileSettings,
  ScoringQueueSummary,
  WorkplaceType,
} from './models'

interface ApiJobSummary {
  job_id: string
  title: string
  company: string
  location: string | null
  workplace_type: WorkplaceType
  job_category: JobCategory | null
  primary_listing_url: string | null
  eligibility_status: EligibilityStatus
  filter_codes: string[]
  coarse_score: number | null
  required_years_min?: number | null
  required_years_max?: number | null
  is_new_grad?: boolean | null
  new_grad_signals?: string[] | null
  requirement_keywords?: string[] | null
  first_discovered_run_id: string
  posted_at: string | null
  first_seen_at: string
  sources: string[]
  created_at: string
  updated_at: string
  last_seen_at: string
  lifecycle_status: 'active' | 'stale' | 'archived'
}

interface ApiListing {
  listing_id: string
  source: string
  source_url: string
  apply_url: string | null
  posted_at: string | null
  posted_at_raw: string | null
  posted_at_quality: string
  first_seen_at: string
  last_seen_at: string
  status: string
}

interface ApiJobDetail extends ApiJobSummary {
  description: string | null
  description_chars: number
  coarse_score_reasoning: string | null
  score_model: string | null
  scored_at: string | null
  listings: ApiListing[]
}

interface ApiJobPage {
  schema_version: string
  items: ApiJobSummary[]
  total: number
}

interface ApiRunSummary {
  run_id: string; discovered_at: string; new_jobs_count: number; observed_count: number
  eligible_count: number; review_count: number; excluded_count: number; error_count: number
  sources: string[]; status: string
}

interface ApiRunPage {
  items: ApiRunSummary[]
}

interface ApiScoringQueue {
  eligible_total: number; scored_current: number; pending: number
  queued: number; failed: number; archived_skipped: number
}

interface ApiBootstrap {
  schema_version: string
  jobs: ApiJobPage
  runs: ApiRunPage
  user_state: ApiUserState
  scoring_profile: ApiScoringProfile | null
  scoring_queue: ApiScoringQueue
}

interface ApiUserState {
  jobs: Array<{
    job_id: string
    status: JobUserStatus
    first_viewed_at: string | null
    last_viewed_at: string | null
    updated_at: string
    coarse_score: number | null
    coarse_score_reasoning: string | null
    score_model: string | null
    score_version: string | null
    profile_version: number | null
    scored_at: string | null
    scoring_status: string | null
    scoring_profile_version: number | null
    score_error: string | null
  }>
  runs: Array<{ run_id: string; viewed_at: string }>
}

export class ApiJobDataSource implements JobDataSource {
  constructor(private readonly baseUrl: string, private readonly tokenProvider: () => string | null) {}

  async getBootstrap(): Promise<DashboardBootstrap> {
    try {
      const payload = await this.request<ApiBootstrap>('/bootstrap?limit=500')
      return {
        jobs: payload.jobs.items.map(toSummary),
        runs: payload.runs.items.map(toRunSummary),
        userState: toUserState(payload.user_state),
        scoringProfile: payload.scoring_profile ? toScoringProfile(payload.scoring_profile) : emptyScoringProfile(),
        scoringQueue: toScoringQueue(payload.scoring_queue),
      }
    } catch (error) {
      // Frontend and API deploy as separate workflows in one concurrency
      // group, so a frontend that lands first would 404 here and fail the
      // whole first paint. Drop this fallback once /bootstrap is live.
      if (!(error instanceof JobApiError) || error.status !== 404) throw error
      const [jobs, runs, userState, scoringProfile, scoringQueue] = await Promise.all([
        this.listJobs(), this.listRuns(), this.getUserState(), this.getScoringProfile(), this.getScoringQueue(),
      ])
      return { jobs, runs, userState, scoringProfile, scoringQueue }
    }
  }

  async listJobs(): Promise<DashboardJobSummary[]> {
    const page = await this.request<ApiJobPage>('/jobs?limit=500')
    return page.items.map(toSummary)
  }

  async getJob(jobId: string): Promise<DashboardJob | null> {
    try {
      const job = await this.request<ApiJobDetail>(`/jobs/${encodeURIComponent(jobId)}`)
      return toDetail(job)
    } catch (error) {
      if (error instanceof JobApiError && error.status === 404) return null
      throw error
    }
  }

  async listRuns(): Promise<DashboardRunSummary[]> {
    const page = await this.request<ApiRunPage>('/runs')
    return page.items.map(toRunSummary)
  }

  async getScoringQueue(): Promise<ScoringQueueSummary> {
    return toScoringQueue(await this.request<ApiScoringQueue>('/scoring/queue'))
  }

  async scoreJob(jobId: string): Promise<void> {
    await this.request(`/jobs/${encodeURIComponent(jobId)}/score`, { method: 'POST' })
  }

  async scoreRun(runId: string, limit: number): Promise<ManualScoringResult> {
    const result = await this.request<ApiManualScoringResult>('/actions/scoring', {
      method: 'POST',
      body: JSON.stringify({ run_id: runId, limit }),
    })
    return {
      runId: result.run_id,
      eligible: result.eligible,
      remaining: result.remaining,
      queued: result.queued,
    }
  }

  async runCrawler(crawler: 'workday' | 'jobspy' | 'both'): Promise<ManualCrawlerResult> {
    const result = await this.request<ApiManualCrawlerResult>('/actions/crawler', {
      method: 'POST',
      body: JSON.stringify({ crawler }),
    })
    return { runId: result.run_id, crawlers: result.crawlers }
  }

  async getUserState(): Promise<DashboardUserState> {
    return toUserState(await this.request<ApiUserState>('/user-state'))
  }

  async markJobViewed(jobId: string): Promise<void> {
    await this.request(`/jobs/${encodeURIComponent(jobId)}/viewed`, { method: 'PUT' })
  }

  async setJobStatus(jobId: string, status: JobUserStatus): Promise<void> {
    await this.request(`/jobs/${encodeURIComponent(jobId)}/state`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    })
  }

  async markRunViewed(runId: string): Promise<void> {
    await this.request(`/runs/${encodeURIComponent(runId)}/viewed`, { method: 'PUT' })
  }

  async getScoringProfile(): Promise<ScoringProfileSettings> {
    const response = await this.request<{ profile: ApiScoringProfile | null }>('/profile/scoring')
    return response.profile ? toScoringProfile(response.profile) : emptyScoringProfile()
  }

  async saveScoringProfile(profile: ScoringProfileSettings): Promise<ScoringProfileSettings> {
    const saved = await this.request<ApiScoringProfile>('/profile/scoring', {
      method: 'PUT',
      body: JSON.stringify({
        skills: profile.skills,
        target_titles: profile.targetTitles,
        min_years_experience: profile.minYearsExperience,
        location_preference: profile.locationPreference || null,
        prefers_new_grad: profile.prefersNewGrad,
        active: profile.active,
      }),
    })
    return toScoringProfile(saved)
  }

  async getDiscoverySettings(): Promise<DiscoverySettings> {
    return toDiscoverySettings(await this.request<ApiDiscoverySettings>('/settings/discovery'))
  }

  async saveDiscoverySettings(settings: DiscoverySettings): Promise<DiscoverySettings> {
    const saved = await this.request<ApiDiscoverySettings>('/settings/discovery', {
      method: 'PUT', body: JSON.stringify({
        search_terms: settings.searchTerms, jobspy_location: settings.jobspyLocation,
        hours_old: settings.hoursOld, jobspy_max_results: settings.jobspyMaxResults,
        workday_max_results: settings.workdayMaxResults, sites: settings.sites,
        accepted_locations: settings.acceptedLocations, include_title_keywords: settings.includeTitleKeywords,
        exclude_title_keywords: settings.excludeTitleKeywords, review_title_keywords: settings.reviewTitleKeywords,
        min_description_chars: settings.minDescriptionChars,
        max_required_years: settings.maxRequiredYears,
      }),
    })
    return toDiscoverySettings(saved)
  }

  private async request<T = { ok: boolean }>(path: string, init: RequestInit = {}): Promise<T> {
    const token = this.tokenProvider()
    const response = await fetch(`${this.baseUrl.replace(/\/$/, '')}${path}`, {
      ...init,
      headers: {
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    })
    if (response.status === 401) {
      localStorage.removeItem('token')
      window.location.assign('/auth')
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText })) as { detail?: string }
      throw new JobApiError(response.status, body.detail ?? response.statusText)
    }
    return response.json() as Promise<T>
  }
}

interface ApiScoringProfile {
  skills: string[]
  target_titles: string[]
  min_years_experience: number | null
  location_preference: string | null
  prefers_new_grad?: boolean | null
  active: boolean
  profile_version: number
  updated_at: string
}

interface ApiManualScoringResult {
  run_id: string
  eligible: number
  remaining: number
  queued: number
}

interface ApiManualCrawlerResult {
  run_id: string
  crawlers: Array<'workday' | 'jobspy'>
}

interface ApiDiscoverySettings {
  search_terms: string[]
  jobspy_location: string
  hours_old: number
  jobspy_max_results: number
  workday_max_results: number
  sites: string[]
  accepted_locations: string[]
  include_title_keywords: string[]
  exclude_title_keywords: string[]
  review_title_keywords: string[]
  min_description_chars: number
  max_required_years?: number | null
  config_version: number
  updated_at: string | null
}

function emptyScoringProfile(): ScoringProfileSettings {
  return { skills: [], targetTitles: [], minYearsExperience: null, locationPreference: '', prefersNewGrad: false, active: true, profileVersion: null, updatedAt: null }
}

function toScoringProfile(profile: ApiScoringProfile): ScoringProfileSettings {
  return { skills: profile.skills, targetTitles: profile.target_titles, minYearsExperience: profile.min_years_experience, locationPreference: profile.location_preference ?? '', prefersNewGrad: profile.prefers_new_grad ?? false, active: profile.active, profileVersion: profile.profile_version, updatedAt: profile.updated_at }
}

function toDiscoverySettings(settings: ApiDiscoverySettings): DiscoverySettings {
  return {
    searchTerms: settings.search_terms, jobspyLocation: settings.jobspy_location, hoursOld: settings.hours_old,
    jobspyMaxResults: settings.jobspy_max_results, workdayMaxResults: settings.workday_max_results,
    sites: settings.sites, acceptedLocations: settings.accepted_locations,
    includeTitleKeywords: settings.include_title_keywords, excludeTitleKeywords: settings.exclude_title_keywords,
    reviewTitleKeywords: settings.review_title_keywords, minDescriptionChars: settings.min_description_chars,
    maxRequiredYears: settings.max_required_years ?? null,
    configVersion: settings.config_version, updatedAt: settings.updated_at,
  }
}

class JobApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
  }
}

function toRunSummary(run: ApiRunSummary): DashboardRunSummary {
  return {
    runId: run.run_id,
    discoveredAt: run.discovered_at,
    newJobsCount: run.new_jobs_count,
    observedCount: run.observed_count,
    eligibleCount: run.eligible_count,
    reviewCount: run.review_count,
    excludedCount: run.excluded_count,
    errorCount: run.error_count,
    sources: run.sources,
    status: run.status,
  }
}

function toScoringQueue(queue: ApiScoringQueue): ScoringQueueSummary {
  return {
    eligibleTotal: queue.eligible_total,
    scoredCurrent: queue.scored_current,
    pending: queue.pending,
    queued: queue.queued,
    failed: queue.failed,
    archivedSkipped: queue.archived_skipped,
  }
}

function toUserState(state: ApiUserState): DashboardUserState {
  return {
    jobs: state.jobs.map((job) => ({
      jobId: job.job_id,
      status: job.status,
      firstViewedAt: job.first_viewed_at,
      lastViewedAt: job.last_viewed_at,
      updatedAt: job.updated_at,
      coarseScore: job.coarse_score,
      coarseScoreReasoning: job.coarse_score_reasoning,
      scoreModel: job.score_model,
      scoreVersion: job.score_version,
      profileVersion: job.profile_version,
      scoredAt: job.scored_at,
      scoringStatus: job.scoring_status,
      scoringProfileVersion: job.scoring_profile_version,
      scoreError: job.score_error,
    })),
    runs: state.runs.map((run) => ({ runId: run.run_id, viewedAt: run.viewed_at })),
  }
}

function toSummary(job: ApiJobSummary): DashboardJobSummary {
  return {
    jobId: job.job_id,
    title: job.title,
    company: job.company,
    location: job.location ?? 'Location unavailable',
    workplaceType: job.workplace_type,
    jobCategory: job.job_category ?? null,
    primaryListingUrl: job.primary_listing_url ?? null,
    eligibilityStatus: job.eligibility_status,
    filterCodes: job.filter_codes,
    coarseScore: job.coarse_score,
    requiredYearsMin: job.required_years_min ?? null,
    requiredYearsMax: job.required_years_max ?? null,
    isNewGrad: job.is_new_grad ?? false,
    newGradSignals: job.new_grad_signals ?? [],
    requirementKeywords: job.requirement_keywords ?? [],
    firstDiscoveredRunId: job.first_discovered_run_id,
    postedAt: job.posted_at,
    firstSeenAt: job.first_seen_at,
    sources: job.sources,
    createdAt: job.created_at,
    updatedAt: job.updated_at,
    lastSeenAt: job.last_seen_at,
    lifecycleStatus: job.lifecycle_status,
  }
}

function toDetail(job: ApiJobDetail): DashboardJob {
  const listings = job.listings.map((listing): JobListing => ({
    listingId: listing.listing_id,
    jobId: job.job_id,
    source: listing.source,
    sourceUrl: listing.source_url,
    applyUrl: listing.apply_url ?? '',
    postedAt: listing.posted_at,
    postedAtRaw: listing.posted_at_raw,
    postedAtQuality: listing.posted_at_quality,
    firstSeenAt: listing.first_seen_at,
    lastSeenAt: listing.last_seen_at,
    status: listing.status,
  }))
  const primaryListing = listings.find((listing) => listing.status === 'active') ?? listings[0] ?? null
  return {
    ...toSummary(job),
    description: job.description ?? '',
    descriptionChars: job.description_chars,
    coarseScoreReasoning: job.coarse_score_reasoning,
    scoreModel: job.score_model,
    scoredAt: job.scored_at,
    listings,
    primaryListing,
  }
}
