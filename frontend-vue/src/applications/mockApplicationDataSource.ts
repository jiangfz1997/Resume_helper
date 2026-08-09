import type {
  ApplicationDataSource,
  ApplicationStatus,
  CreateApplicationFromJob,
  JobApplication,
  UpdateApplicationFields,
} from './models'

const STORAGE_KEY = 'candidate-profile:applications:v1'

export class MockApplicationDataSource implements ApplicationDataSource {
  async listApplications(status?: ApplicationStatus): Promise<JobApplication[]> {
    const applications = load()
    const filtered = status ? applications.filter((application) => application.status === status) : applications
    return [...filtered].sort((left, right) => Date.parse(right.appliedAt) - Date.parse(left.appliedAt))
  }

  async createFromJob(data: CreateApplicationFromJob): Promise<JobApplication> {
    const now = new Date().toISOString()
    const application: JobApplication = {
      applicationId: crypto.randomUUID(),
      sourceType: 'dashboard',
      jobId: data.jobId ?? null,
      sourceUrl: data.sourceUrl ?? null,
      applyUrl: data.applyUrl ?? null,
      company: data.company,
      title: data.title,
      location: data.location ?? null,
      jdText: data.jdText,
      status: 'applied',
      statusHistory: [{ status: 'applied', note: null, changedAt: now }],
      extractionStatus: 'ready',
      extractionError: null,
      notes: null,
      appliedAt: now,
      createdAt: now,
      updatedAt: now,
    }
    save([application, ...load()])
    return application
  }

  async createFromUrl(url: string): Promise<JobApplication> {
    const now = new Date().toISOString()
    const application: JobApplication = {
      applicationId: crypto.randomUUID(),
      sourceType: 'manual',
      jobId: null,
      sourceUrl: url,
      applyUrl: null,
      company: 'Pasted link',
      title: 'Local dev preview (no extraction worker)',
      location: null,
      jdText: `Mock data source: paste-URL extraction is not simulated locally. Original link: ${url}`,
      status: 'applied',
      statusHistory: [{ status: 'applied', note: null, changedAt: now }],
      extractionStatus: 'ready',
      extractionError: null,
      notes: null,
      appliedAt: now,
      createdAt: now,
      updatedAt: now,
    }
    save([application, ...load()])
    return application
  }

  async updateStatus(applicationId: string, status: ApplicationStatus, note?: string): Promise<JobApplication> {
    const now = new Date().toISOString()
    const applications = load()
    const updated = applications.map((application) => application.applicationId === applicationId
      ? {
          ...application,
          status,
          updatedAt: now,
          statusHistory: [...application.statusHistory, { status, note: note ?? null, changedAt: now }],
        }
      : application)
    save(updated)
    const result = updated.find((application) => application.applicationId === applicationId)
    if (!result) throw new Error('application not found')
    return result
  }

  async updateFields(applicationId: string, data: UpdateApplicationFields): Promise<JobApplication> {
    const now = new Date().toISOString()
    const applications = load()
    const updated = applications.map((application) => application.applicationId === applicationId
      ? {
          ...application,
          ...(data.company !== undefined ? { company: data.company } : {}),
          ...(data.title !== undefined ? { title: data.title } : {}),
          ...(data.location !== undefined ? { location: data.location } : {}),
          ...(data.notes !== undefined ? { notes: data.notes } : {}),
          updatedAt: now,
        }
      : application)
    save(updated)
    const result = updated.find((application) => application.applicationId === applicationId)
    if (!result) throw new Error('application not found')
    return result
  }

  async deleteApplication(applicationId: string): Promise<void> {
    save(load().filter((application) => application.applicationId !== applicationId))
  }

  async refreshApplication(applicationId: string): Promise<JobApplication | null> {
    return load().find((application) => application.applicationId === applicationId) ?? null
  }
}

function load(): JobApplication[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? (parsed as JobApplication[]) : []
  } catch {
    return []
  }
}

function save(applications: JobApplication[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(applications))
}
