import type { JobCategory } from './models'

// Mirrors job_discovery/domain/filters.py's SDE_TITLE_KEYWORDS / QA_TITLE_KEYWORDS.
// Only used by the local mock data source, which has no job_category column --
// the real API already tags each job at ingestion time.
const SDE_TITLE_KEYWORDS = [
  'software engineer', 'software developer', 'backend', 'back-end', 'back end',
  'frontend', 'front-end', 'front end', 'full stack', 'full-stack', 'fullstack',
  'developer', 'sde', 'swe',
]
const QA_TITLE_KEYWORDS = [
  'qa engineer', 'quality assurance', 'qa analyst', 'sdet',
  'test engineer', 'test automation', 'automation engineer',
]

export function classifyJobCategory(title: string): JobCategory | null {
  const normalized = title.toLowerCase()
  if (QA_TITLE_KEYWORDS.some((keyword) => normalized.includes(keyword))) return 'qa'
  if (SDE_TITLE_KEYWORDS.some((keyword) => normalized.includes(keyword))) return 'sde'
  return null
}
