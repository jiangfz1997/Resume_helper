import { defineStore } from 'pinia'
import type { JobUserStatus } from '../jobs/models'

const STORAGE_KEY = 'job-dashboard:user-statuses:v1'

function loadStatuses(): Record<string, JobUserStatus> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed as Record<string, JobUserStatus> : {}
  } catch {
    return {}
  }
}

export const useJobsStore = defineStore('jobs', {
  state: () => ({
    statuses: loadStatuses(),
  }),
  actions: {
    statusFor(jobId: string): JobUserStatus {
      return this.statuses[jobId] ?? 'new'
    },
    setStatus(jobId: string, status: JobUserStatus): void {
      this.statuses = { ...this.statuses, [jobId]: status }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.statuses))
    },
  },
})
