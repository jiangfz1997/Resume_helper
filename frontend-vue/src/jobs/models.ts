export type EligibilityStatus = 'eligible' | 'review' | 'excluded'
export type WorkplaceType = 'remote' | 'hybrid' | 'onsite' | 'unknown'
export type JobUserStatus = 'new' | 'saved' | 'selected' | 'applied' | 'rejected'

export interface JobRecord {
  jobId: string
  company: string
  location: string
  title: string
  description: string
  descriptionChars: number
  eligibilityStatus: EligibilityStatus
  filterCodes: string[]
  workplaceType: WorkplaceType
  coarseScore: number | null
  requiredYearsMin: number | null
  requiredYearsMax: number | null
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
  eligibilityStatus: EligibilityStatus
  filterCodes: string[]
  workplaceType: WorkplaceType
  coarseScore: number | null
  requiredYearsMin: number | null
  requiredYearsMax: number | null
  requirementKeywords: string[]
  firstDiscoveredRunId: string
  postedAt: string | null
  firstSeenAt: string
  sources: string[]
  createdAt: string
  updatedAt: string
}

export interface DashboardRunSummary {
  runId: string
  discoveredAt: string
  newJobsCount: number
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
  configVersion: number | null
  updatedAt: string | null
}

export interface DashboardJob extends DashboardJobSummary, JobRecord {
  listings: JobListing[]
  primaryListing: JobListing | null
}

export interface JobDataSource {
  listJobs(): Promise<DashboardJobSummary[]>
  getJob(jobId: string): Promise<DashboardJob | null>
  listRuns(): Promise<DashboardRunSummary[]>
  getUserState(): Promise<DashboardUserState>
  markJobViewed(jobId: string): Promise<void>
  setJobStatus(jobId: string, status: JobUserStatus): Promise<void>
  markRunViewed(runId: string): Promise<void>
  getScoringProfile(): Promise<ScoringProfileSettings>
  saveScoringProfile(profile: ScoringProfileSettings): Promise<ScoringProfileSettings>
  getDiscoverySettings(): Promise<DiscoverySettings>
  saveDiscoverySettings(settings: DiscoverySettings): Promise<DiscoverySettings>
}
