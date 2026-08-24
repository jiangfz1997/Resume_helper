export interface SkillDefinition {
  name: string
  patterns: RegExp[]
}

export interface SkillDocument {
  id: string
  title: string
  company: string
  date: string | null
  source: 'market' | 'applied'
  keywords: string[]
}

export interface SkillStat {
  name: string
  count: number
  rate: number
}

// Keep the vocabulary deterministic so market and application samples are
// comparable. Patterns deliberately avoid ambiguous bare terms such as
// "go" and "rest", which otherwise create many false positives in prose.
export const SKILL_DEFINITIONS: SkillDefinition[] = [
  { name: 'Python', patterns: [/(?<![a-z])python(?![a-z])/i] },
  { name: 'Java', patterns: [/(?<![a-z])java(?!script|[a-z])/i] },
  { name: 'JavaScript', patterns: [/(?<![a-z])javascript(?![a-z])/i, /(?<![a-z])js(?![a-z])/i] },
  { name: 'TypeScript', patterns: [/(?<![a-z])typescript(?![a-z])/i, /(?<![a-z])ts(?![a-z])/i] },
  { name: 'C#', patterns: [/(?<![a-z])c#(?![a-z])/i] },
  { name: 'C++', patterns: [/(?<![a-z])c\+\+(?![a-z])/i] },
  { name: 'Go', patterns: [/(?<![a-z])golang(?![a-z])/i, /(?<![a-z])go programming language(?![a-z])/i] },
  { name: 'Ruby', patterns: [/(?<![a-z])ruby(?![a-z])/i] },
  { name: 'PHP', patterns: [/(?<![a-z])php(?![a-z])/i] },
  { name: 'Kotlin', patterns: [/(?<![a-z])kotlin(?![a-z])/i] },
  { name: 'Swift', patterns: [/(?<![a-z])swift(?![a-z])/i] },
  { name: 'Scala', patterns: [/(?<![a-z])scala(?![a-z])/i] },
  { name: 'Rust', patterns: [/(?<![a-z])rust(?![a-z])/i] },
  { name: 'HTML', patterns: [/(?<![a-z])html5?(?![a-z])/i] },
  { name: 'CSS', patterns: [/(?<![a-z])css3?(?![a-z])/i] },
  { name: 'Bash', patterns: [/(?<![a-z])bash(?![a-z])/i, /shell scripting/i] },
  { name: 'SQL', patterns: [/(?<![a-z])sql(?![a-z])/i, /(?<![a-z])postgres(?:ql)?(?![a-z])/i, /(?<![a-z])mysql(?![a-z])/i] },
  { name: 'React', patterns: [/(?<![a-z])react(?:\.js)?(?![a-z])/i] },
  { name: 'Angular', patterns: [/(?<![a-z])angular(?![a-z])/i] },
  { name: 'Vue', patterns: [/(?<![a-z])vue(?:\.js)?(?![a-z])/i] },
  { name: 'Node.js', patterns: [/(?<![a-z])node\.js(?![a-z])/i, /(?<![a-z])nodejs(?![a-z])/i] },
  { name: '.NET', patterns: [/(?<![a-z])\.net(?![a-z])/i, /(?<![a-z])asp\.net(?![a-z])/i] },
  { name: 'Spring', patterns: [/(?<![a-z])spring(?: boot)?(?![a-z])/i] },
  { name: 'Django', patterns: [/(?<![a-z])django(?![a-z])/i] },
  { name: 'Flask', patterns: [/(?<![a-z])flask(?![a-z])/i] },
  { name: 'FastAPI', patterns: [/(?<![a-z])fastapi(?![a-z])/i] },
  { name: 'AWS', patterns: [/(?<![a-z])aws(?![a-z])/i, /amazon web services/i] },
  { name: 'Azure', patterns: [/(?<![a-z])azure(?![a-z])/i] },
  { name: 'GCP', patterns: [/(?<![a-z])gcp(?![a-z])/i, /google cloud(?: platform)?/i] },
  { name: 'Docker', patterns: [/(?<![a-z])docker(?![a-z])/i] },
  { name: 'Kubernetes', patterns: [/(?<![a-z])kubernetes(?![a-z])/i, /(?<![a-z])k8s(?![a-z])/i] },
  { name: 'Terraform', patterns: [/(?<![a-z])terraform(?![a-z])/i] },
  { name: 'Jenkins', patterns: [/(?<![a-z])jenkins(?![a-z])/i] },
  { name: 'Git', patterns: [/(?<![a-z])git(?:hub|lab)?(?![a-z])/i] },
  { name: 'CI/CD', patterns: [/(?<![a-z])ci\s*\/\s*cd(?![a-z])/i, /continuous integration/i, /continuous (?:delivery|deployment)/i] },
  { name: 'Linux', patterns: [/(?<![a-z])linux(?![a-z])/i] },
  { name: 'REST API', patterns: [/(?<![a-z])restful(?: apis?| services?)?(?![a-z])/i, /(?<![a-z])rest apis?(?![a-z])/i] },
  { name: 'GraphQL', patterns: [/(?<![a-z])graphql(?![a-z])/i] },
  { name: 'Microservices', patterns: [/(?<![a-z])microservices?(?![a-z])/i] },
  { name: 'Kafka', patterns: [/(?<![a-z])(?:apache )?kafka(?![a-z])/i] },
  { name: 'Spark', patterns: [/(?<![a-z])(?:apache )?spark(?![a-z])/i] },
  { name: 'Snowflake', patterns: [/(?<![a-z])snowflake(?![a-z])/i] },
  { name: 'Databricks', patterns: [/(?<![a-z])databricks(?![a-z])/i] },
  { name: 'MongoDB', patterns: [/(?<![a-z])mongodb(?![a-z])/i] },
  { name: 'Redis', patterns: [/(?<![a-z])redis(?![a-z])/i] },
  { name: 'Elasticsearch', patterns: [/(?<![a-z])elasticsearch(?![a-z])/i] },
  { name: 'Oracle', patterns: [/(?<![a-z])oracle(?![a-z])/i] },
  { name: 'Salesforce', patterns: [/(?<![a-z])salesforce(?![a-z])/i] },
  { name: 'PyTorch', patterns: [/(?<![a-z])pytorch(?![a-z])/i] },
  { name: 'TensorFlow', patterns: [/(?<![a-z])tensorflow(?![a-z])/i] },
  { name: 'Selenium', patterns: [/(?<![a-z])selenium(?![a-z])/i] },
  { name: 'Cypress', patterns: [/(?<![a-z])cypress(?![a-z])/i] },
  { name: 'Playwright', patterns: [/(?<![a-z])playwright(?![a-z])/i] },
  { name: 'Jest', patterns: [/(?<![a-z])jest(?![a-z])/i] },
]

export function extractSkills(text: string): string[] {
  if (!text.trim()) return []
  return SKILL_DEFINITIONS
    .filter((definition) => definition.patterns.some((pattern) => pattern.test(text)))
    .map((definition) => definition.name)
}

export function normalizeSkills(keywords: string[]): string[] {
  return extractSkills(keywords.join('\n'))
}

export function aggregateSkills(documents: SkillDocument[]): SkillStat[] {
  if (!documents.length) return []
  const counts = new Map<string, number>()
  for (const document of documents) {
    for (const keyword of new Set(document.keywords)) {
      counts.set(keyword, (counts.get(keyword) ?? 0) + 1)
    }
  }
  return [...counts.entries()]
    .map(([name, count]) => ({
      name,
      count,
      rate: Math.round((count / documents.length) * 1000) / 10,
    }))
    .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name))
}

export function isWithinDays(date: string | null, days: number | null, now = Date.now()): boolean {
  if (days === null) return true
  if (!date) return false
  const timestamp = Date.parse(date)
  if (!Number.isFinite(timestamp)) return false
  return timestamp >= now - days * 24 * 60 * 60 * 1000
}
