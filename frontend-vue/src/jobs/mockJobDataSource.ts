import listingsCsv from '../mocks/job-listings.csv?raw'
import recordsCsv from '../mocks/job-records.csv?raw'
import { cleanExportedString, nullableString, parseCsv } from './csv'
import type {
  DashboardJob,
  DashboardJobSummary,
  EligibilityStatus,
  JobDataSource,
  JobListing,
  JobRecord,
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

function toRecord(row: Record<string, string>): JobRecord {
  return {
    jobId: row.job_id,
    company: cleanExportedString(row.canonical_company) || 'Unknown company',
    location: cleanExportedString(row.canonical_location) || 'Location unavailable',
    title: cleanExportedString(row.canonical_title) || 'Untitled role',
    description: cleanExportedString(row.description),
    descriptionChars: Number(row.description_chars) || 0,
    eligibilityStatus: (row.eligibility_status || 'review') as EligibilityStatus,
    filterCodes: parseFilterCodes(row.filter_codes),
    workplaceType: (row.workplace_type || 'unknown') as WorkplaceType,
    coarseScore: parseScore(row.coarse_score),
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
      return {
        ...record,
        postedAt: selectPrimaryListing(jobListings)?.postedAt ?? null,
        firstSeenAt: jobListings.map((listing) => listing.firstSeenAt).sort()[0] ?? record.createdAt,
        sources: [...new Set(jobListings.map((listing) => listing.source))].sort(),
        listings: jobListings,
        primaryListing: selectPrimaryListing(jobListings),
      }
    })
  }

  async listJobs(): Promise<DashboardJobSummary[]> {
    return this.jobs
  }

  async getJob(jobId: string): Promise<DashboardJob | null> {
    return this.jobs.find((job) => job.jobId === jobId) ?? null
  }
}
