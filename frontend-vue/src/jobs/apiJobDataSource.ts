import type {
  DashboardJob,
  DashboardJobSummary,
  EligibilityStatus,
  JobDataSource,
  JobListing,
  WorkplaceType,
} from './models'

interface ApiJobSummary {
  job_id: string
  title: string
  company: string
  location: string | null
  workplace_type: WorkplaceType
  eligibility_status: EligibilityStatus
  filter_codes: string[]
  coarse_score: number | null
  posted_at: string | null
  first_seen_at: string
  sources: string[]
  created_at: string
  updated_at: string
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

export class ApiJobDataSource implements JobDataSource {
  constructor(private readonly baseUrl: string, private readonly tokenProvider: () => string | null) {}

  async listJobs(): Promise<DashboardJobSummary[]> {
    const page = await this.request<ApiJobPage>('/jobs?limit=100')
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

  private async request<T>(path: string): Promise<T> {
    const token = this.tokenProvider()
    const response = await fetch(`${this.baseUrl.replace(/\/$/, '')}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
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

class JobApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
  }
}

function toSummary(job: ApiJobSummary): DashboardJobSummary {
  return {
    jobId: job.job_id,
    title: job.title,
    company: job.company,
    location: job.location ?? 'Location unavailable',
    workplaceType: job.workplace_type,
    eligibilityStatus: job.eligibility_status,
    filterCodes: job.filter_codes,
    coarseScore: job.coarse_score,
    postedAt: job.posted_at,
    firstSeenAt: job.first_seen_at,
    sources: job.sources,
    createdAt: job.created_at,
    updatedAt: job.updated_at,
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
