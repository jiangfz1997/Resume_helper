import type { CandidateProfile, CandidateProfileInput, ProfileDataSource } from './models'

export class ApiProfileDataSource implements ProfileDataSource {
  constructor(private readonly baseUrl: string, private readonly tokenProvider: () => string | null) {}

  async getProfile(): Promise<CandidateProfile | null> {
    const response = await this.request<{ profile: CandidateProfile | null }>('/profile')
    return response.profile
  }

  saveProfile(profile: CandidateProfileInput): Promise<CandidateProfile> {
    return this.request('/profile', {
      method: 'PUT',
      body: JSON.stringify(profile),
    })
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
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
      throw new Error(body.detail ?? response.statusText)
    }
    return response.json() as Promise<T>
  }
}
