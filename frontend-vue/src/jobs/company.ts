// Mirrors domain.normalize.normalize_company on the backend. Company blocking
// is an exact match on the normalized name, so both sides must agree on it or
// a locally hidden company would reappear on the next load.
export function normalizeCompany(company: string): string {
  return company.trim().split(/\s+/).join(' ').toLowerCase()
}
