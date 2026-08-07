import type {
  ApplicationDataSource,
  ApplicationStats,
  ApplicationStatus,
  CreateApplicationFromJob,
  JobApplication,
  UpdateApplicationFields,
} from './models'

interface ApiStatusEvent {
  status: ApplicationStatus
  note: string | null
  changed_at: string
}

interface ApiApplication {
  application_id: string
  source_type: 'dashboard' | 'manual'
  job_id: string | null
  source_url: string | null
  apply_url: string | null
  company: string
  title: string
  location: string | null
  jd_text: string
  raw_html: string | null
  status: ApplicationStatus
  status_history: ApiStatusEvent[]
  extraction_status: 'ready' | 'extracting' | 'failed'
  extraction_error: string | null
  notes: string | null
  applied_at: string
  created_at: string
  updated_at: string
}

interface ApiStats {
  today: number
  this_week: number
  total: number
  by_status: Partial<Record<ApplicationStatus, number>>
}

export class ApiApplicationDataSource implements ApplicationDataSource {
  constructor(private readonly baseUrl: string, private readonly tokenProvider: () => string | null) {}

  async listApplications(status?: ApplicationStatus): Promise<JobApplication[]> {
    const query = status ? `?status=${encodeURIComponent(status)}` : ''
    const page = await this.request<{ items: ApiApplication[] }>(`/applications${query}`)
    return page.items.map(toApplication)
  }

  async getStats(): Promise<ApplicationStats> {
    const stats = await this.request<ApiStats>('/applications/stats')
    return { today: stats.today, thisWeek: stats.this_week, total: stats.total, byStatus: stats.by_status }
  }

  async createFromJob(data: CreateApplicationFromJob): Promise<JobApplication> {
    const created = await this.request<ApiApplication>('/applications/from-job', {
      method: 'POST',
      body: JSON.stringify({
        job_id: data.jobId ?? null,
        source_url: data.sourceUrl ?? null,
        apply_url: data.applyUrl ?? null,
        company: data.company,
        title: data.title,
        location: data.location ?? null,
        jd_text: data.jdText,
      }),
    })
    return toApplication(created)
  }

  async createFromUrl(url: string): Promise<JobApplication> {
    const created = await this.request<ApiApplication>('/applications/from-url', {
      method: 'POST',
      body: JSON.stringify({ url }),
    })
    return toApplication(created)
  }

  async updateStatus(applicationId: string, status: ApplicationStatus, note?: string): Promise<JobApplication> {
    const updated = await this.request<ApiApplication>(`/applications/${encodeURIComponent(applicationId)}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, note: note ?? null }),
    })
    return toApplication(updated)
  }

  async updateFields(applicationId: string, data: UpdateApplicationFields): Promise<JobApplication> {
    const updated = await this.request<ApiApplication>(`/applications/${encodeURIComponent(applicationId)}`, {
      method: 'PATCH',
      body: JSON.stringify({
        company: data.company,
        title: data.title,
        location: data.location,
        notes: data.notes,
      }),
    })
    return toApplication(updated)
  }

  async deleteApplication(applicationId: string): Promise<void> {
    await this.request(`/applications/${encodeURIComponent(applicationId)}`, { method: 'DELETE' })
  }

  async refreshApplication(applicationId: string): Promise<JobApplication | null> {
    try {
      return toApplication(await this.request<ApiApplication>(`/applications/${encodeURIComponent(applicationId)}`))
    } catch (error) {
      if (error instanceof ApplicationApiError && error.status === 404) return null
      throw error
    }
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
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText })) as { detail?: string }
      throw new ApplicationApiError(response.status, body.detail ?? response.statusText)
    }
    return response.json() as Promise<T>
  }
}

class ApplicationApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
  }
}

function toApplication(item: ApiApplication): JobApplication {
  return {
    applicationId: item.application_id,
    sourceType: item.source_type,
    jobId: item.job_id,
    sourceUrl: item.source_url,
    applyUrl: item.apply_url,
    company: item.company,
    title: item.title,
    location: item.location,
    jdText: item.jd_text,
    rawHtml: item.raw_html,
    status: item.status,
    statusHistory: item.status_history.map((event) => ({
      status: event.status,
      note: event.note,
      changedAt: event.changed_at,
    })),
    extractionStatus: item.extraction_status,
    extractionError: item.extraction_error,
    notes: item.notes,
    appliedAt: item.applied_at,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
  }
}
