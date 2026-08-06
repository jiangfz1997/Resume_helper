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
          </div>
          <n-form-item label="Include in scheduled scoring"><n-switch v-model:value="profile.active" /></n-form-item>
        </n-form>
        <footer><small>{{ profileMeta }}</small><n-button type="primary" :loading="savingProfile" @click="saveProfile">Save my profile</n-button></footer>
      </n-card>

      <n-card title="Shared discovery settings" size="small">
        <n-alert type="warning" :show-icon="false" class="shared-warning">Changes here affect both users. They are picked up by the next crawler run.</n-alert>
        <n-form label-placement="top">
          <n-form-item label="Search terms"><n-input v-model:value="searchTerms" type="textarea" :rows="3" placeholder="Software Engineer, SDET, QA Engineer" /></n-form-item>
          <div class="three-column">
            <n-form-item label="JobSpy location"><n-input v-model:value="discovery.jobspyLocation" /></n-form-item>
            <n-form-item label="Posted within (hours)"><n-input-number v-model:value="discovery.hoursOld" :min="1" :max="168" /></n-form-item>
            <n-form-item label="Minimum JD characters"><n-input-number v-model:value="discovery.minDescriptionChars" :min="0" :max="10000" /></n-form-item>
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
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { jobDataSource } from '../jobs/dataSource'
import type { DiscoverySettings, ScoringProfileSettings } from '../jobs/models'

const message = useMessage()
const loading = ref(true)
const loadError = ref('')
const savingProfile = ref(false)
const savingDiscovery = ref(false)
const profile = ref<ScoringProfileSettings>(emptyProfile())
const discovery = ref<DiscoverySettings>(emptyDiscovery())
const profileSkills = ref('')
const profileTitles = ref('')
const searchTerms = ref('')
const acceptedLocations = ref('')
const includeKeywords = ref('')
const excludeKeywords = ref('')
const reviewKeywords = ref('')

const profileMeta = computed(() => profile.value.profileVersion ? `Profile v${profile.value.profileVersion} · ${formatDate(profile.value.updatedAt)}` : 'Not saved yet')
const discoveryMeta = computed(() => discovery.value.configVersion ? `Shared config v${discovery.value.configVersion} · ${formatDate(discovery.value.updatedAt)}` : 'Using system defaults')

onMounted(async () => {
  try {
    const [loadedProfile, loadedDiscovery] = await Promise.all([jobDataSource.getScoringProfile(), jobDataSource.getDiscoverySettings()])
    profile.value = loadedProfile
    discovery.value = loadedDiscovery
    profileSkills.value = loadedProfile.skills.join(', ')
    profileTitles.value = loadedProfile.targetTitles.join(', ')
    searchTerms.value = loadedDiscovery.searchTerms.join(', ')
    acceptedLocations.value = loadedDiscovery.acceptedLocations.join(', ')
    includeKeywords.value = loadedDiscovery.includeTitleKeywords.join(', ')
    excludeKeywords.value = loadedDiscovery.excludeTitleKeywords.join(', ')
    reviewKeywords.value = loadedDiscovery.reviewTitleKeywords.join(', ')
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

function splitList(value: string): string[] { return [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))] }
function formatDate(value: string | null): string { return value ? new Intl.DateTimeFormat('en-CA', { dateStyle: 'medium', timeStyle: 'short' }).format(Date.parse(value)) : '' }
function emptyProfile(): ScoringProfileSettings { return { skills: [], targetTitles: [], minYearsExperience: null, locationPreference: '', active: true, profileVersion: null, updatedAt: null } }
function emptyDiscovery(): DiscoverySettings { return { searchTerms: [], jobspyLocation: 'Canada', hoursOld: 24, jobspyMaxResults: 15, workdayMaxResults: 10, sites: ['indeed', 'linkedin'], acceptedLocations: [], includeTitleKeywords: [], excludeTitleKeywords: [], reviewTitleKeywords: [], minDescriptionChars: 300, configVersion: null, updatedAt: null } }
</script>

<style scoped>
.settings-page{min-height:calc(100vh - 56px);padding:36px;color:#edf1f7;background:radial-gradient(circle at 8% -15%,rgba(58,121,255,.15),transparent 32%),#0b0d12;box-sizing:border-box}.settings-page>header,.settings-grid{max-width:1280px;margin:auto}.settings-page>header{margin-bottom:24px}.eyebrow{color:#6fa8ff;font:700 10px/1.3 monospace;letter-spacing:.16em}.settings-page h1{margin:8px 0 6px;font-size:34px;letter-spacing:-.035em}.settings-page header p,.hint{margin:0;color:#8e98a9;font-size:13px}.settings-grid{display:grid;grid-template-columns:minmax(360px,.8fr) minmax(500px,1.2fr);gap:16px}.hint{margin-bottom:18px}.shared-warning{margin-bottom:18px}.two-column,.three-column{display:grid;gap:12px}.two-column{grid-template-columns:1fr 1fr}.three-column{grid-template-columns:1fr 1fr 1fr}.settings-grid footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:10px;border-top:1px solid rgba(255,255,255,.08)}.settings-grid footer small{color:#687487}.loading{display:grid;place-items:center;height:400px}@media(max-width:980px){.settings-grid{grid-template-columns:1fr}.settings-page{padding:24px 18px}}@media(max-width:650px){.two-column,.three-column{grid-template-columns:1fr}}
</style>
