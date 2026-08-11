export type ProficiencyLevel = 'expert' | 'intermediate' | 'beginner'

export interface ContactInfo {
  email?: string | null
  phone?: string | null
  location?: string | null
  linkedin?: string | null
  github?: string | null
  website?: string | null
}

export interface WorkExperience {
  id?: string
  company?: string
  title?: string
  location?: string
  start_date?: string
  end_date?: string | null
  bullets?: string[]
}

export interface Education {
  institution?: string
  degree?: string
  field_of_study?: string
  start_date?: string
  end_date?: string | null
  gpa?: string | null
}

export interface Project {
  id?: string
  name?: string
  description?: string
  bullets?: string[]
  tech_stack?: string[]
  url?: string | null
}

export interface Skill {
  category: string
  name: string
  proficiency?: ProficiencyLevel | null
}

export interface CandidateProfileInput {
  schema_version?: 1
  full_name: string
  summary?: string | null
  contact_info?: ContactInfo | null
  work_experiences?: WorkExperience[]
  educations?: Education[]
  projects?: Project[]
  skills?: Skill[]
}

export interface CandidateProfile extends CandidateProfileInput {
  schema_version?: 1
  user_id: string
  profile_version?: number
  updated_at: string
  work_experiences: WorkExperience[]
  educations: Education[]
  projects: Project[]
  skills: Skill[]
}

export interface ProfileDataSource {
  getProfile(): Promise<CandidateProfile | null>
  saveProfile(profile: CandidateProfileInput): Promise<CandidateProfile>
}
