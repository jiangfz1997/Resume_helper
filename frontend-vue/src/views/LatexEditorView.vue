<template>
  <div :style="{ display: 'flex', flexDirection: 'column', height: containerHeight }">

    <!-- Toolbar -->
    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; margin-bottom: 8px; border-bottom: 1px solid #2e2e2e; flex-shrink: 0">
      <n-space align="center" size="small">
        <n-text style="font-family: monospace; font-size: 13px; color: #7eb8f7">resume.tex</n-text>
        <n-divider vertical />
        <n-button
          size="small"
          type="primary"
          :loading="status === 'compiling'"
          :disabled="!latexContent.trim()"
          @click="triggerCompile"
        >
          Compile
        </n-button>
        <n-text depth="3" style="font-size: 11px">auto 3s after edit</n-text>
        <n-tag v-if="status === 'success'" type="success" size="small">{{ lastCompileAt }}</n-tag>
        <n-tag v-if="status === 'error'" type="error" size="small">Compile error</n-tag>
      </n-space>

      <n-space size="small">
        <n-button size="small" quaternary @click="copyLatex">Copy LaTeX</n-button>
        <n-button size="small" :disabled="!pdfBlob" @click="downloadPdf">Download PDF</n-button>
      </n-space>
    </div>

    <!-- Split pane -->
    <div style="display: flex; flex: 1; gap: 8px; overflow: hidden; min-height: 0">

      <!-- Left: Monaco editor -->
      <div style="flex: 1; overflow: hidden; border: 1px solid #2e2e2e; min-width: 0">
        <VueMonacoEditor
          v-model:value="latexContent"
          language="plaintext"
          theme="vs-dark"
          :options="monacoOptions"
          style="height: 100%"
        />
      </div>

      <!-- Right: PDF viewer -->
      <div
        ref="viewerPane"
        style="flex: 1; overflow-y: auto; background: #141414; border: 1px solid #2e2e2e; padding: 16px; min-width: 0"
      >
        <!-- idle -->
        <div
          v-if="status === 'idle'"
          style="display: flex; align-items: center; justify-content: center; height: 100%"
        >
          <n-text depth="3" style="font-size: 13px; text-align: center">
            Click Compile or start editing<br />to see the PDF preview
          </n-text>
        </div>

        <!-- compiling overlay -->
        <div
          v-else-if="status === 'compiling'"
          style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 16px"
        >
          <n-spin size="large" />
          <n-text depth="3">Compiling...</n-text>
        </div>

        <!-- compile error -->
        <n-alert v-else-if="status === 'error'" type="error" title="Compilation failed" style="font-size: 12px">
          <pre style="white-space: pre-wrap; font-family: monospace; font-size: 11px; margin: 8px 0 0">{{ compileError }}</pre>
        </n-alert>

        <!-- PDF pages (always mounted so ref is stable) -->
        <div v-show="status === 'success'" ref="canvasContainer" />
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import * as pdfjsLib from 'pdfjs-dist'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { compileLatex } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useEditorStore } from '../stores/editor'

// ── PDF.js worker ──────────────────────────────────────────────
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).href

// ── state ──────────────────────────────────────────────────────
const auth = useAuthStore()
const editorStore = useEditorStore()
const token = () => auth.token!

const latexContent = ref(editorStore.latexContent)
const canvasContainer = ref<HTMLDivElement | null>(null)
const viewerPane = ref<HTMLDivElement | null>(null)
const pdfBlob = ref<Blob | null>(null)

type Status = 'idle' | 'compiling' | 'success' | 'error'
const status = ref<Status>('idle')
const compileError = ref('')
const lastCompileAt = ref('')

// Keep store in sync when user edits
watch(latexContent, (val) => editorStore.setContent(val))

// ── layout height ──────────────────────────────────────────────
// 56px nav + 24px top padding + 36px toolbar + 8px gap + 24px bottom padding
const containerHeight = computed(() => 'calc(100vh - 148px)')

// ── monaco options ─────────────────────────────────────────────
const monacoOptions = {
  minimap: { enabled: false },
  fontSize: 13,
  lineNumbers: 'on' as const,
  wordWrap: 'on' as const,
  scrollBeyondLastLine: false,
  tabSize: 2,
  fontFamily: '"Cascadia Code", "Fira Code", Consolas, monospace',
  renderLineHighlight: 'all' as const,
}

// ── compile ────────────────────────────────────────────────────
async function triggerCompile(): Promise<void> {
  if (!latexContent.value.trim()) return
  status.value = 'compiling'
  compileError.value = ''
  try {
    const blob = await compileLatex(token(), latexContent.value)
    pdfBlob.value = blob
    await renderPDF(blob)
    status.value = 'success'
    lastCompileAt.value = new Date().toLocaleTimeString()
  } catch (e) {
    compileError.value = (e as Error).message
    status.value = 'error'
  }
}

// ── PDF rendering ──────────────────────────────────────────────
async function renderPDF(blob: Blob): Promise<void> {
  const container = canvasContainer.value
  if (!container) return

  const arrayBuffer = await blob.arrayBuffer()
  const pdfDoc = await pdfjsLib.getDocument({ data: new Uint8Array(arrayBuffer) }).promise

  container.innerHTML = ''
  const containerWidth = (viewerPane.value?.clientWidth ?? 480) - 32

  for (let i = 1; i <= pdfDoc.numPages; i++) {
    const page = await pdfDoc.getPage(i)
    const baseViewport = page.getViewport({ scale: 1 })
    const scale = containerWidth / baseViewport.width
    const viewport = page.getViewport({ scale })

    const canvas = document.createElement('canvas')
    canvas.width = viewport.width
    canvas.height = viewport.height
    canvas.style.display = 'block'
    canvas.style.marginBottom = '12px'
    canvas.style.boxShadow = '0 2px 12px rgba(0,0,0,0.6)'

    const ctx = canvas.getContext('2d')
    if (!ctx) continue
    await page.render({ canvas, canvasContext: ctx, viewport }).promise
    container.appendChild(canvas)
  }
}

// ── debounce auto-compile ──────────────────────────────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null

watch(latexContent, () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(triggerCompile, 3000)
})

onUnmounted(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
})

// ── initial compile if content already loaded from store ───────
onMounted(() => {
  if (latexContent.value.trim()) triggerCompile()
})

// ── actions ────────────────────────────────────────────────────
function copyLatex(): void {
  navigator.clipboard.writeText(latexContent.value)
}

function downloadPdf(): void {
  if (!pdfBlob.value) return
  const a = document.createElement('a')
  a.href = URL.createObjectURL(pdfBlob.value)
  a.download = 'resume.pdf'
  a.click()
}
</script>
