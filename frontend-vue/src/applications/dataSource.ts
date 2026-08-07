import { ApiApplicationDataSource } from './apiApplicationDataSource'
import { MockApplicationDataSource } from './mockApplicationDataSource'
import type { ApplicationDataSource } from './models'

const mode = import.meta.env.VITE_JOB_DATA_SOURCE ?? 'mock'

export const applicationDataSource: ApplicationDataSource = mode === 'api'
  ? new ApiApplicationDataSource(
      requiredEnvironment('VITE_APPLICATIONS_API_URL', import.meta.env.VITE_APPLICATIONS_API_URL),
      () => localStorage.getItem('token'),
    )
  : new MockApplicationDataSource()

function requiredEnvironment(name: string, value: string | undefined): string {
  if (!value) throw new Error(`${name} is required when VITE_JOB_DATA_SOURCE=api`)
  return value
}
