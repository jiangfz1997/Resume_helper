import { ApiJobDataSource } from './apiJobDataSource'
import { MockJobDataSource } from './mockJobDataSource'
import type { JobDataSource } from './models'

const mode = import.meta.env.VITE_JOB_DATA_SOURCE ?? 'mock'

export const jobDataSource: JobDataSource = mode === 'api'
  ? new ApiJobDataSource(
      requiredEnvironment('VITE_JOBS_API_URL', import.meta.env.VITE_JOBS_API_URL),
      () => localStorage.getItem('token'),
    )
  : new MockJobDataSource()

function requiredEnvironment(name: string, value: string | undefined): string {
  if (!value) throw new Error(`${name} is required when VITE_JOB_DATA_SOURCE=api`)
  return value
}
