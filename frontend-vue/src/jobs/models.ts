export type EligibilityStatus = 'eligible' | 'review' | 'excluded'
export type WorkplaceType = 'remote' | 'hybrid' | 'onsite' | 'unknown'
export type JobUserStatus = 'new' | 'saved' | 'selected' | 'applied' | 'rejected'
export type JobCategory = 'sde' | 'qa'
export type JobLifecycleStatus = 'active' | 'stale' | 'archived'

export interface JobRecord {
  jobId: string
  company: string
  location: string
  title: string
  description: string
  descriptionChars: number
  jobCategory: JobCategory | null
  eligibilityStatus: EligibilityStatus
  filterCodes: string[]
  workplaceType: WorkplaceType
  coarseScore: number | null
  requiredYearsMin: number | null
  requiredYearsMax: number | null
  isNewGrad: boolean
  newGradSignals: string[]
  requirementKeywords: string[]
  coarseScoreReasoning: string | null
  scoreModel: string | null
  scoredAt: string | null
  createdAt: string
  updatedAt: string
}

export interface JobListing {
  listingId: string
  jobId: string
  source: string
  sourceUrl: string
  applyUrl: string
  postedAt: string | null
  postedAtRaw: string | null
  postedAtQuality: string
  firstSeenAt: string
  lastSeenAt: string
  status: string
}

export interface DashboardJobSummary {
  jobId: string
  company: string
  location: string
  title: string
  jobCategory: JobCategory | null
  primaryListingUrl: string | null
  eligibilityStatus: EligibilityStatus
  filterCodes: string[]
  workplaceType: WorkplaceType
  coarseScore: number | null
  requiredYearsMin: number | null
  requiredYearsMax: number | null
  isNewGrad: boolean
  newGradSignals: string[]
  requirementKeywords: string[]
  firstDiscoveredRunId: string
  postedAt: string | null
  firstSeenAt: string
  sources: string[]
  createdAt: string
  updatedAt: string
  lastSeenAt: string
  lifecycleStatus: JobLifecycleStatus
}

export interface DashboardRunSummary {
  runId: string
  discoveredAt: string
  newJobsCount: number
  observedCount: number
  eligibleCount: number
  reviewCount: number
  excludedCount: number
  errorCount: number
  sources: string[]
  status: string
}

export interface ScoringQueueSummary {
  eligibleTotal: number
  scoredCurrent: number
  pending: number
  queued: number
  failed: number
  archivedSkipped: number
}

export interface JobUserState {
  jobId: string
  status: JobUserStatus
  firstViewedAt: string | null
  lastViewedAt: string | null
  updatedAt: string
  coarseScore: number | null
  coarseScoreReasoning: string | null
  scoreModel: string | null
  scoreVersion: string | null
  profileVersion: number | null
  scoredAt: string | null
  scoringStatus: string | null
  scoringProfileVersion: number | null
  scoreError: string | null
}

export interface RunUserState {
  runId: string
  viewedAt: string
}

export interface DashboardUserState {
  jobs: JobUserState[]
  runs: RunUserState[]
}

export interface ScoringProfileSettings {
  skills: string[]
  targetTitles: string[]
  minYearsExperience: number | null
  locationPreference: string
  prefersNewGrad: boolean
  active: boolean
  profileVersion: number | null
  updatedAt: string | null
}

export interface DiscoverySettings {
  searchTerms: string[]
  jobspyLocation: string
  hoursOld: number
  jobspyMaxResults: number
  workdayMaxResults: number
  sites: string[]
  acceptedLocations: string[]
  includeTitleKeywords: string[]
  excludeTitleKeywords: string[]
  reviewTitleKeywords: string[]
  minDescriptionChars: number
  maxRequiredYears: number | null
  configVersion: number | null
  updatedAt: string | null
}

export interface ManualScoringResult {
  runId: string
  eligible: number
  remaining: number
  queued: number
}

export interface ManualCrawlerResult {
  runId: string
  crawlers: Array<'workday' | 'jobspy'>
}

export interface DashboardJob extends DashboardJobSummary, JobRecord {
  listings: JobListing[]
  primaryListing: JobListing | null
}

export interface DashboardBootstrap {
  jobs: DashboardJobSummary[]
  runs: DashboardRunSummary[]
  userState: DashboardUserState
  scoringProfile: ScoringProfileSettings
  scoringQueue: ScoringQueueSummary
}

export interface JobDataSource {
  getBootstrap(): Promise<DashboardBootstrap>
  listJobs(): Promise<DashboardJobSummary[]>
  getJob(jobId: string): Promise<DashboardJob | null>
  listRuns(): Promise<DashboardRunSummary[]>
  getScoringQueue(): Promise<ScoringQueueSummary>
  scoreJob(jobId: string): Promise<void>
  scoreRun(runId: string, limit: number): Promise<ManualScoringResult>
  runCrawler(crawler: 'workday' | 'jobspy' | 'both'): Promise<ManualCrawlerResult>
  getUserState(): Promise<DashboardUserState>
  markJobViewed(jobId: string): Promise<void>
  setJobStatus(jobId: string, status: JobUserStatus): Promise<void>
  markRunViewed(runId: string): Promise<void>
  getScoringProfile(): Promise<ScoringProfileSettings>
  saveScoringProfile(profile: ScoringProfileSettings): Promise<ScoringProfileSettings>
  getDiscoverySettings(): Promise<DiscoverySettings>
  saveDiscoverySettings(settings: DiscoverySettings): Promise<DiscoverySettings>
}
