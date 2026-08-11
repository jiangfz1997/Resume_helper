import { ApiProfileDataSource } from './apiProfileDataSource'
import type { ProfileDataSource } from './models'

export const profileDataSource: ProfileDataSource = new ApiProfileDataSource(
  requiredEnvironment('VITE_APPLICATIONS_API_URL', import.meta.env.VITE_APPLICATIONS_API_URL),
  () => localStorage.getItem('token'),
)

function requiredEnvironment(name: string, value: string | undefined): string {
  if (!value) throw new Error(`${name} is required for the candidate profile API`)
  return value
}
