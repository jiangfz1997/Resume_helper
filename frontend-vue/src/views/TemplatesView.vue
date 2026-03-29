<template>
  <div>
    <!-- DEPRECATED: LaTeX template workflow is no longer active. This page is kept for reference only. -->
    <n-alert type="warning" style="margin-bottom: 20px">
      Templates are currently unavailable. The LaTeX-based template workflow has been deprecated.
    </n-alert>
    <n-space vertical size="large">

      <!-- Upload card -->
      <n-card title="Upload Template">
        <n-space vertical size="medium">
          <n-grid :cols="2" :x-gap="16" :y-gap="12">
            <n-gi>
              <n-form-item label="Name" :show-feedback="false">
                <n-input v-model:value="form.name" placeholder="e.g. Software Engineer Classic" />
              </n-form-item>
            </n-gi>
            <n-gi>
              <n-form-item label="Industry" :show-feedback="false">
                <n-input v-model:value="form.industry" placeholder="e.g. Tech, Finance" />
              </n-form-item>
            </n-gi>
            <n-gi>
              <n-form-item label="Style Tag" :show-feedback="false">
                <n-input v-model:value="form.style_tag" placeholder="e.g. minimal, modern" />
              </n-form-item>
            </n-gi>
            <n-gi>
              <n-form-item label="Description" :show-feedback="false">
                <n-input v-model:value="form.description" placeholder="Short description" />
              </n-form-item>
            </n-gi>
          </n-grid>

          <n-form-item label=".tex Preamble File" :show-feedback="false">
            <n-upload accept=".tex" :max="1" :show-file-list="true" @change="onFileChange">
              <n-upload-dragger style="padding: 16px">
                <n-text depth="3" style="font-size: 13px">
                  Drop a <code>.tex</code> file here, or click to select
                </n-text>
              </n-upload-dragger>
            </n-upload>
          </n-form-item>

          <n-space>
            <n-button type="primary" :loading="uploading" :disabled="!canSubmit" @click="submitTemplate">
              Save Template
            </n-button>
            <n-button quaternary @click="resetForm">Clear</n-button>
          </n-space>

          <n-alert v-if="uploadError" type="error" :title="uploadError" />
        </n-space>
      </n-card>

      <!-- Global templates -->
      <n-card title="Global Templates">
        <n-spin v-if="loading" />
        <n-empty v-else-if="globalTemplates.length === 0" description="No global templates yet" />
        <n-space v-else vertical size="small">
          <div
            v-for="t in globalTemplates"
            :key="t.id"
            style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border:1px solid #2e2e2e;border-radius:6px"
          >
            <div style="display:flex;flex-direction:column;gap:4px">
              <n-space align="center" size="small">
                <span style="font-size:14px;font-weight:500">{{ t.name }}</span>
                <n-tag type="info" size="tiny">global</n-tag>
              </n-space>
              <span style="font-size:11px;color:#888">{{ metaLine(t) }}</span>
            </div>
            <n-button size="small" type="primary" @click="useTemplate(t)">Use in Editor</n-button>
          </div>
        </n-space>
      </n-card>

      <!-- My templates -->
      <n-card title="My Templates">
        <n-spin v-if="loading" />
        <n-empty v-else-if="myTemplates.length === 0" description="No custom templates yet" />
        <n-space v-else vertical size="small">
          <div
            v-for="t in myTemplates"
            :key="t.id"
            style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border:1px solid #2e2e2e;border-radius:6px"
          >
            <div style="display:flex;flex-direction:column;gap:4px">
              <n-space align="center" size="small">
                <span style="font-size:14px;font-weight:500">{{ t.name }}</span>
                <n-tag type="default" size="tiny">custom</n-tag>
              </n-space>
              <span style="font-size:11px;color:#888">{{ metaLine(t) }}</span>
            </div>
            <n-space size="small">
              <n-button size="small" type="primary" @click="useTemplate(t)">Use in Editor</n-button>
              <n-button size="small" type="error" quaternary @click="deleteTemplate(t)">Delete</n-button>
            </n-space>
          </div>
        </n-space>
      </n-card>

    </n-space>
  </div>
</template>

<script setup lang="ts">
import { useMessage } from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  createUserTemplate,
  deleteUserTemplate,
  listTemplates,
  type TemplateRead,
} from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useEditorStore } from '../stores/editor'

const auth = useAuthStore()
const editorStore = useEditorStore()
const router = useRouter()
const message = useMessage()

const token = () => auth.token!

// ── state ──────────────────────────────────────────────────────
const templates = ref<TemplateRead[]>([])
const loading = ref(false)
const uploading = ref(false)
const uploadError = ref('')

const globalTemplates = computed(() => templates.value.filter(t => t.source === 'global'))
const myTemplates = computed(() => templates.value.filter(t => t.source === 'user'))

// ── form ───────────────────────────────────────────────────────
const form = ref({ name: '', industry: '', style_tag: '', description: '' })
const preambleContent = ref('')
const bodyExampleContent = ref('')

const canSubmit = computed(() => form.value.name.trim() && preambleContent.value.trim())

function splitTex(raw: string): { preamble: string; body_example: string } {
  const beginIdx = raw.indexOf('\\begin{document}')
  if (beginIdx === -1) return { preamble: raw.trim(), body_example: '' }
  const preamble = raw.slice(0, beginIdx).trim()
  const afterBegin = raw.slice(beginIdx + '\\begin{document}'.length)
  const endIdx = afterBegin.lastIndexOf('\\end{document}')
  const body_example = (endIdx === -1 ? afterBegin : afterBegin.slice(0, endIdx)).trim()
  return { preamble, body_example }
}

function onFileChange({ fileList }: { fileList: UploadFileInfo[] }): void {
  const item = fileList[fileList.length - 1]
  if (!item?.file) { preambleContent.value = ''; bodyExampleContent.value = ''; return }
  const reader = new FileReader()
  reader.onload = (e) => {
    const raw = (e.target?.result as string) ?? ''
    const { preamble, body_example } = splitTex(raw)
    preambleContent.value = preamble
    bodyExampleContent.value = body_example
  }
  reader.readAsText(item.file)
}

function resetForm(): void {
  form.value = { name: '', industry: '', style_tag: '', description: '' }
  preambleContent.value = ''
  bodyExampleContent.value = ''
  uploadError.value = ''
}

async function submitTemplate(): Promise<void> {
  if (!canSubmit.value) return
  uploading.value = true
  uploadError.value = ''
  try {
    const created = await createUserTemplate(token(), {
      name: form.value.name.trim(),
      industry: form.value.industry.trim() || undefined,
      style_tag: form.value.style_tag.trim() || undefined,
      description: form.value.description.trim() || undefined,
      preamble: preambleContent.value,
      body_example: bodyExampleContent.value || undefined,
    })
    templates.value.push(created)
    message.success(`Template saved — preamble ${preambleContent.value.length} chars, body example ${bodyExampleContent.value.length} chars`)
    resetForm()
  } catch (e) {
    uploadError.value = (e as Error).message
  } finally {
    uploading.value = false
  }
}

// ── load ───────────────────────────────────────────────────────
async function fetchTemplates(): Promise<void> {
  loading.value = true
  try {
    templates.value = await listTemplates(token())
  } finally {
    loading.value = false
  }
}

onMounted(fetchTemplates)

// ── actions ────────────────────────────────────────────────────
function useTemplate(t: TemplateRead): void {
  editorStore.setContent(t.preamble)
  router.push('/editor')
}

async function deleteTemplate(t: TemplateRead): Promise<void> {
  try {
    await deleteUserTemplate(token(), t.id)
    templates.value = templates.value.filter(x => x.id !== t.id)
    message.success('Template deleted')
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e)
    if (detail.toLowerCase().includes('json') || detail.toLowerCase().includes('unexpected')) {
      // 204 No Content parsed as JSON — the deletion actually succeeded
      templates.value = templates.value.filter(x => x.id !== t.id)
      message.success('Template deleted')
    } else {
      message.error(`Failed to delete template: ${detail}`)
    }
  }
}

function metaLine(t: TemplateRead): string {
  return [t.industry, t.style_tag, t.description].filter(Boolean).join(' · ')
}
</script>
