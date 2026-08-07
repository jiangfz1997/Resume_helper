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
  rawHtml: string | null
  status: ApplicationStatus
  statusHistory: ApplicationStatusEvent[]
  extractionStatus: ExtractionStatus
  extractionError: string | null
  notes: string | null
  appliedAt: string
  createdAt: string
  updatedAt: string
}

export interface ApplicationStats {
  today: number
  thisWeek: number
  total: number
  byStatus: Partial<Record<ApplicationStatus, number>>
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
  getStats(): Promise<ApplicationStats>
  createFromJob(data: CreateApplicationFromJob): Promise<JobApplication>
  createFromUrl(url: string): Promise<JobApplication>
  updateStatus(applicationId: string, status: ApplicationStatus, note?: string): Promise<JobApplication>
  updateFields(applicationId: string, data: UpdateApplicationFields): Promise<JobApplication>
  deleteApplication(applicationId: string): Promise<void>
  refreshApplication(applicationId: string): Promise<JobApplication | null>
}
