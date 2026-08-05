export type EligibilityStatus = 'eligible' | 'review' | 'excluded'
export type WorkplaceType = 'remote' | 'hybrid' | 'onsite' | 'unknown'
export type JobUserStatus = 'new' | 'saved' | 'selected' | 'rejected'

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
  postedAt: string | null
  firstSeenAt: string
  sources: string[]
  createdAt: string
  updatedAt: string
}

export interface DashboardJob extends DashboardJobSummary, JobRecord {
  listings: JobListing[]
  primaryListing: JobListing | null
}

export interface JobDataSource {
  listJobs(): Promise<DashboardJobSummary[]>
  getJob(jobId: string): Promise<DashboardJob | null>
}
