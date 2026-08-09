export type ApplicationSourceType = 'dashboard' | 'manual'
export type ApplicationStatus =
  | 'applied'
  | 'resume_rejected'
  | 'interviewing'
  | 'interview_rejected'
  | 'offer'
  | 'accepted'
  | 'withdrawn'
export type ExtractionStatus = 'ready' | 'extracting' | 'failed'

export interface ApplicationStatusEvent {
  status: ApplicationStatus
  note: string | null
  changedAt: string
}

export interface JobApplication {
  applicationId: string
  sourceType: ApplicationSourceType
  jobId: string | null
  sourceUrl: string | null
  applyUrl: string | null
  company: string
  title: string
  location: string | null
  jdText: string
  status: ApplicationStatus
  statusHistory: ApplicationStatusEvent[]
  extractionStatus: ExtractionStatus
  extractionError: string | null
  notes: string | null
  appliedAt: string
  createdAt: string
  updatedAt: string
}

/** Derived on the client from a loaded application list, never fetched. */
export interface ApplicationStats {
  today: number
  thisWeek: number
  total: number
  byStatus: Partial<Record<ApplicationStatus, number>>
}

/** Counts for the header tiles. Week starts Monday, in the viewer's timezone. */
export function deriveStats(applications: JobApplication[]): ApplicationStats {
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const weekStart = new Date(todayStart)
  weekStart.setDate(weekStart.getDate() - ((weekStart.getDay() + 6) % 7))
  const byStatus: Partial<Record<ApplicationStatus, number>> = {}
  let today = 0
  let thisWeek = 0
  for (const application of applications) {
    const appliedAt = Date.parse(application.appliedAt)
    if (appliedAt >= todayStart.getTime()) today += 1
    if (appliedAt >= weekStart.getTime()) thisWeek += 1
    byStatus[application.status] = (byStatus[application.status] ?? 0) + 1
  }
  return { today, thisWeek, total: applications.length, byStatus }
}

export interface CreateApplicationFromJob {
  jobId?: string | null
  sourceUrl?: string | null
  applyUrl?: string | null
  company: string
  title: string
  location?: string | null
  jdText: string
}

export interface UpdateApplicationFields {
  company?: string
  title?: string
  location?: string | null
  notes?: string | null
}

export interface ApplicationDataSource {
  listApplications(status?: ApplicationStatus): Promise<JobApplication[]>
  createFromJob(data: CreateApplicationFromJob): Promise<JobApplication>
  createFromUrl(url: string): Promise<JobApplication>
  updateStatus(applicationId: string, status: ApplicationStatus, note?: string): Promise<JobApplication>
  updateFields(applicationId: string, data: UpdateApplicationFields): Promise<JobApplication>
  deleteApplication(applicationId: string): Promise<void>
  refreshApplication(applicationId: string): Promise<JobApplication | null>
}
