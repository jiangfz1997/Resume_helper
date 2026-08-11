<template>
  <main class="settings-page">
    <header>
      <div>
        <span class="eyebrow">JOB DISCOVERY / SETTINGS</span>
        <h1>Profiles are personal. Discovery is shared.</h1>
        <p>Your scoring profile affects only your scores. Search changes affect both users and the next scheduled crawl.</p>
      </div>
    </header>

    <n-alert v-if="loadError" type="error">{{ loadError }}</n-alert>
    <div v-else-if="loading" class="loading"><n-spin size="large" /></div>
    <section v-else class="settings-grid">
      <n-card title="My scoring profile" size="small">
        <p class="hint">Saved under your signed-in account and used by the personalized scoring Lambda.</p>
        <n-form label-placement="top">
          <n-form-item label="Target titles"><n-input v-model:value="profileTitles" type="textarea" :rows="3" placeholder="Software Engineer, Backend Developer, SDET" /></n-form-item>
          <n-form-item label="Skills"><n-input v-model:value="profileSkills" type="textarea" :rows="4" placeholder="Python, TypeScript, AWS, Playwright" /></n-form-item>
          <div class="two-column">
            <n-form-item label="Years of experience"><n-input-number v-model:value="profile.minYearsExperience" :min="0" :max="50" clearable /></n-form-item>
            <n-form-item label="Location preference"><n-input v-model:value="profile.locationPreference" placeholder="Toronto / Remote Canada" /></n-form-item>
            <n-form-item label="Prefer new-grad roles"><n-switch v-model:value="profile.prefersNewGrad" /></n-form-item>
          </div>
          <n-form-item label="Include in scheduled scoring"><n-switch v-model:value="profile.active" /></n-form-item>
        </n-form>
        <footer><small>{{ profileMeta }}</small><n-button type="primary" :loading="savingProfile" @click="saveProfile">Save my profile</n-button></footer>
      </n-card>

      <n-card title="Blocked companies" size="small">
        <p class="hint">Yours alone. Their postings are hidden from your inbox and never sent for scoring; other accounts still see them.</p>
        <n-empty v-if="!blockedCompanies.length" description="Nothing blocked yet. Use the ⊘ button on any role." size="small" />
        <div v-else class="blocked-list">
          <n-tag
            v-for="company in blockedCompanies"
            :key="company"
            closable
            :disabled="unblocking === company"
            @close="unblockCompany(company)"
          >{{ company }}</n-tag>
        </div>
      </n-card>

      <n-card title="Shared discovery settings" size="small">
        <n-alert type="warning" :show-icon="false" class="shared-warning">Changes here affect both users. They are picked up by the next crawler run.</n-alert>
        <n-form label-placement="top">
          <n-form-item label="Search terms"><n-input v-model:value="searchTerms" type="textarea" :rows="3" placeholder="Software Engineer, SDET, QA Engineer" /></n-form-item>
          <div class="three-column">
            <n-form-item label="JobSpy location"><n-input v-model:value="discovery.jobspyLocation" /></n-form-item>
            <n-form-item label="Posted within (hours)"><n-input-number v-model:value="discovery.hoursOld" :min="1" :max="168" /></n-form-item>
            <n-form-item label="Minimum JD characters"><n-input-number v-model:value="discovery.minDescriptionChars" :min="0" :max="10000" /></n-form-item>
            <n-form-item label="Max years a posting may require"><n-input-number v-model:value="discovery.maxRequiredYears" :min="0" :max="20" clearable placeholder="No limit" /></n-form-item>
          </div>
          <div class="three-column">
            <n-form-item label="JobSpy results / query"><n-input-number v-model:value="discovery.jobspyMaxResults" :min="1" :max="100" /></n-form-item>
            <n-form-item label="Workday results / employer"><n-input-number v-model:value="discovery.workdayMaxResults" :min="1" :max="100" /></n-form-item>
            <n-form-item label="Sources"><n-checkbox-group v-model:value="discovery.sites"><n-space><n-checkbox value="indeed">Indeed</n-checkbox><n-checkbox value="linkedin">LinkedIn</n-checkbox></n-space></n-checkbox-group></n-form-item>
          </div>
          <n-form-item label="Accepted locations (empty means unrestricted)"><n-input v-model:value="acceptedLocations" placeholder="Toronto, Vancouver, Canada" /></n-form-item>
          <n-form-item label="Relevant title keywords"><n-input v-model:value="includeKeywords" type="textarea" :rows="3" /></n-form-item>
          <n-form-item label="Exclude title keywords"><n-input v-model:value="excludeKeywords" placeholder="staff, principal, director" /></n-form-item>
          <n-form-item label="Send to review"><n-input v-model:value="reviewKeywords" placeholder="senior, sr., lead" /></n-form-item>
        </n-form>
        <footer><small>{{ discoveryMeta }}</small><n-button type="primary" :loading="savingDiscovery" @click="saveDiscovery">Save shared search</n-button></footer>
      </n-card>

      <n-card title="Manual runs" size="small" class="manual-actions">
        <div class="manual-grid">
          <section>
            <h3>Score one discovery run</h3>
            <p class="hint">Queues only eligible jobs from that run for your current profile. Already scored or queued jobs are skipped.</p>
            <n-form label-placement="top">
              <n-form-item label="Discovery run">
                <n-select v-model:value="scoringRunId" :options="runOptions" filterable placeholder="Select a run" />
              </n-form-item>
              <n-form-item label="Maximum jobs (1–100)">
                <n-input-number v-model:value="scoringLimit" :min="1" :max="100" />
              </n-form-item>
            </n-form>
            <n-button type="primary" :disabled="!scoringRunId" :loading="runningScoring" @click="runScoring">Run scoring</n-button>
          </section>
          <section>
            <h3>Run a crawler now</h3>
            <p class="hint">Starts asynchronously with the saved shared discovery settings.</p>
            <n-form label-placement="top">
              <n-form-item label="Crawler">
                <n-select v-model:value="crawler" :options="crawlerOptions" />
              </n-form-item>
            </n-form>
            <n-button type="primary" :loading="runningCrawler" @click="runCrawler">Run crawler</n-button>
          </section>
        </div>
      </n-card>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { jobDataSource } from '../jobs/dataSource'
import type { DashboardRunSummary, DiscoveryCrawler, DiscoverySettings, ScoringProfileSettings } from '../jobs/models'

const message = useMessage()
const loading = ref(true)
const loadError = ref('')
const savingProfile = ref(false)
const savingDiscovery = ref(false)
const runningScoring = ref(false)
const runningCrawler = ref(false)
const profile = ref<ScoringProfileSettings>(emptyProfile())
const discovery = ref<DiscoverySettings>(emptyDiscovery())
const profileSkills = ref('')
const profileTitles = ref('')
const searchTerms = ref('')
const acceptedLocations = ref('')
const includeKeywords = ref('')
const excludeKeywords = ref('')
const reviewKeywords = ref('')
const runs = ref<DashboardRunSummary[]>([])
const blockedCompanies = ref<string[]>([])
const unblocking = ref('')
const scoringRunId = ref<string | null>(null)
const scoringLimit = ref(20)
const crawler = ref<DiscoveryCrawler>('all')

const crawlerOptions = [
  { label: 'All (Workday + JobSpy + New Grad)', value: 'all' },
  { label: 'Both (Workday + JobSpy)', value: 'both' },
  { label: 'New Grad feeds (Simplify + GitHub)', value: 'simplify' },
  { label: 'New Grad · Simplify Canada only', value: 'simplify_canada' },
  { label: 'New Grad · GitHub list only', value: 'simplify_github' },
  { label: 'Workday', value: 'workday' },
  { label: 'JobSpy', value: 'jobspy' },
]
const runOptions = computed(() => runs.value.map((run) => ({
  label: `${formatDate(run.discoveredAt)} · ${run.eligibleCount} eligible · ${run.sources.join(', ')}`,
  value: run.runId,
})))

const profileMeta = computed(() => profile.value.profileVersion ? `Profile v${profile.value.profileVersion} · ${formatDate(profile.value.updatedAt)}` : 'Not saved yet')
const discoveryMeta = computed(() => discovery.value.configVersion ? `Shared config v${discovery.value.configVersion} · ${formatDate(discovery.value.updatedAt)}` : 'Using system defaults')

onMounted(async () => {
  try {
    const [loadedProfile, loadedDiscovery, loadedRuns, loadedBlocklist] = await Promise.all([jobDataSource.getScoringProfile(), jobDataSource.getDiscoverySettings(), jobDataSource.listRuns(), jobDataSource.listBlockedCompanies()])
    profile.value = loadedProfile
    blockedCompanies.value = loadedBlocklist
    discovery.value = loadedDiscovery
    profileSkills.value = loadedProfile.skills.join(', ')
    profileTitles.value = loadedProfile.targetTitles.join(', ')
    searchTerms.value = loadedDiscovery.searchTerms.join(', ')
    acceptedLocations.value = loadedDiscovery.acceptedLocations.join(', ')
    includeKeywords.value = loadedDiscovery.includeTitleKeywords.join(', ')
    excludeKeywords.value = loadedDiscovery.excludeTitleKeywords.join(', ')
    reviewKeywords.value = loadedDiscovery.reviewTitleKeywords.join(', ')
    runs.value = loadedRuns
    scoringRunId.value = loadedRuns[0]?.runId ?? null
  } catch (reason) {
    loadError.value = reason instanceof Error ? reason.message : 'Unable to load settings.'
  } finally {
    loading.value = false
  }
})

async function saveProfile(): Promise<void> {
  savingProfile.value = true
  try {
    profile.value = await jobDataSource.saveScoringProfile({ ...profile.value, skills: splitList(profileSkills.value), targetTitles: splitList(profileTitles.value) })
    message.success('Your scoring profile was saved.')
  } catch (reason) {
    message.error(reason instanceof Error ? reason.message : 'Unable to save profile.')
  } finally {
    savingProfile.value = false
  }
}

async function saveDiscovery(): Promise<void> {
  savingDiscovery.value = true
  try {
    discovery.value = await jobDataSource.saveDiscoverySettings({
      ...discovery.value,
      searchTerms: splitList(searchTerms.value), acceptedLocations: splitList(acceptedLocations.value),
      includeTitleKeywords: splitList(includeKeywords.value), excludeTitleKeywords: splitList(excludeKeywords.value),
      reviewTitleKeywords: splitList(reviewKeywords.value),
    })
    message.success('Shared discovery settings were saved.')
  } catch (reason) {
    message.error(reason instanceof Error ? reason.message : 'Unable to save shared settings.')
  } finally {
    savingDiscovery.value = false
  }
}

async function unblockCompany(company: string): Promise<void> {
  unblocking.value = company
  try {
    blockedCompanies.value = await jobDataSource.unblockCompany(company)
    message.success(`${company} is visible again.`)
  } catch (reason) {
    message.error(reason instanceof Error ? reason.message : `Unable to unblock ${company}.`)
  } finally {
    unblocking.value = ''
  }
}

async function runScoring(): Promise<void> {
  if (!scoringRunId.value) return
  runningScoring.value = true
  try {
    const result = await jobDataSource.scoreRun(scoringRunId.value, scoringLimit.value)
    message.success(result.queued
      ? `Queued ${result.queued} of ${result.remaining} unscored eligible jobs.`
      : `Nothing queued; all ${result.eligible} eligible jobs are already scored or queued.`)
  } catch (reason) {
    message.error(reason instanceof Error ? reason.message : 'Unable to start scoring.')
  } finally {
    runningScoring.value = false
  }
}

async function runCrawler(): Promise<void> {
  runningCrawler.value = true
  try {
    const result = await jobDataSource.runCrawler(crawler.value)
    message.success(`Started ${result.crawlers.join(' + ')} crawler run ${result.runId}.`)
  } catch (reason) {
    message.error(reason instanceof Error ? reason.message : 'Unable to start crawler.')
  } finally {
    runningCrawler.value = false
  }
}

function splitList(value: string): string[] { return [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))] }
function formatDate(value: string | null): string { return value ? new Intl.DateTimeFormat('en-CA', { dateStyle: 'medium', timeStyle: 'short' }).format(Date.parse(value)) : '' }
function emptyProfile(): ScoringProfileSettings { return { skills: [], targetTitles: [], minYearsExperience: null, locationPreference: '', prefersNewGrad: false, active: true, profileVersion: null, updatedAt: null } }
function emptyDiscovery(): DiscoverySettings { return { searchTerms: [], jobspyLocation: 'Canada', hoursOld: 24, jobspyMaxResults: 15, workdayMaxResults: 10, sites: ['indeed', 'linkedin'], acceptedLocations: [], includeTitleKeywords: [], excludeTitleKeywords: [], reviewTitleKeywords: [], minDescriptionChars: 300, maxRequiredYears: null, configVersion: null, updatedAt: null } }
</script>

<style scoped>
.settings-page{min-height:calc(100vh - 56px);padding:36px;color:#edf1f7;background:radial-gradient(circle at 8% -15%,rgba(58,121,255,.15),transparent 32%),#0b0d12;box-sizing:border-box}.settings-page>header,.settings-grid{max-width:1280px;margin:auto}.settings-page>header{margin-bottom:24px}.eyebrow{color:#6fa8ff;font:700 10px/1.3 monospace;letter-spacing:.16em}.settings-page h1{margin:8px 0 6px;font-size:34px;letter-spacing:-.035em}.settings-page header p,.hint{margin:0;color:#8e98a9;font-size:13px}.settings-grid{display:grid;grid-template-columns:minmax(360px,.8fr) minmax(500px,1.2fr);gap:16px}.hint{margin-bottom:18px}.shared-warning{margin-bottom:18px}.blocked-list{display:flex;flex-wrap:wrap;gap:8px}.two-column,.three-column,.manual-grid{display:grid;gap:12px}.two-column{grid-template-columns:1fr 1fr}.three-column{grid-template-columns:1fr 1fr 1fr}.manual-actions{grid-column:1/-1}.manual-grid{grid-template-columns:1fr 1fr;gap:32px}.manual-grid section+section{padding-left:32px;border-left:1px solid rgba(255,255,255,.08)}.manual-grid h3{margin:0 0 8px;font-size:16px}.settings-grid footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:10px;border-top:1px solid rgba(255,255,255,.08)}.settings-grid footer small{color:#687487}.loading{display:grid;place-items:center;height:400px}@media(max-width:980px){.settings-grid{grid-template-columns:1fr}.settings-page{padding:24px 18px}}@media(max-width:650px){.two-column,.three-column,.manual-grid{grid-template-columns:1fr}.manual-grid section+section{padding:24px 0 0;border-top:1px solid rgba(255,255,255,.08);border-left:0}}
</style>
