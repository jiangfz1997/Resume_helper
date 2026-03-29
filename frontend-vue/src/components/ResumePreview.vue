<template>
  <div class="preview-shell">
    <div class="preview-toolbar">
      <n-text depth="3" style="font-size: 12px">A4 Preview</n-text>
      <n-space align="center" size="small">
        <n-spin v-if="loading" size="small" />
        <n-button size="tiny" :loading="exporting" type="primary" @click="doExport">
          Export PDF
        </n-button>
      </n-space>
    </div>
    <div class="preview-scroll">
      <div class="preview-frame-wrap">
        <iframe
          ref="iframeEl"
          class="preview-iframe"
          sandbox="allow-same-origin"
          :srcdoc="htmlContent"
        />
        <!-- A4 page-1 boundary indicator overlay -->
        <div class="page-limit-line" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import type { LayoutSettings, TailoredResumeDraft } from '../api/client'
import { exportPdf, previewHtml } from '../api/client'
import { useAuthStore } from '../stores/auth'

const props = defineProps<{
  draft: TailoredResumeDraft
  settings: LayoutSettings
  fullName: string
}>()

const emit = defineEmits<{ (e: 'section-click', hlValue: string): void }>()

const auth = useAuthStore()
const message = useMessage()
const exporting = ref(false)
const loading = ref(false)
const htmlContent = ref('')
const iframeEl = ref<HTMLIFrameElement | null>(null)

// A4 at 96dpi = 794px wide, 1122px tall.
// The iframe renders at exactly this scale (no zoom), so the preview
// matches what Playwright will produce pixel-for-pixel.
const A4_W = 794
const A4_H = 1123

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function attachDblclickListener(): void {
  const doc = iframeEl.value?.contentDocument
  if (!doc) return
  doc.addEventListener('dblclick', (e: MouseEvent) => {
    let el = e.target as HTMLElement | null
    while (el && el !== doc.body) {
      const hl = el.getAttribute('data-hl')
      if (hl) { emit('section-click', hl); return }
      el = el.parentElement
    }
  })
}

async function fetchPreview(): Promise<void> {
  if (!auth.token) return
  loading.value = true
  try {
    htmlContent.value = await previewHtml(auth.token, props.draft, props.settings, props.fullName)
  } catch {
    // non-critical: keep last rendered content
  } finally {
    loading.value = false
    // srcdoc replacement triggers iframe reload; attach after load settles
    const iframe = iframeEl.value
    if (iframe) {
      iframe.onload = () => { attachDblclickListener() }
    }
  }
}

function schedulePreview(): void {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(fetchPreview, 400)
}

watch(() => [props.draft, props.settings, props.fullName] as const, schedulePreview, {
  deep: true,
  immediate: true,
})

function highlightByHl(hlValue: string | null): void {
  const doc = iframeEl.value?.contentDocument
  if (!doc) return
  let styleEl = doc.getElementById('hl-style') as HTMLStyleElement | null
  if (!styleEl) {
    styleEl = doc.createElement('style')
    styleEl.id = 'hl-style'
    doc.head?.appendChild(styleEl)
  }
  styleEl.textContent = hlValue
    ? `[data-hl="${hlValue}"] { outline: 2px solid rgba(99,179,237,0.85); outline-offset: 2px; background: rgba(99,179,237,0.10); border-radius: 2px; }`
    : ''
}

defineExpose({ highlightByHl })

async function doExport(): Promise<void> {
  exporting.value = true
  try {
    const blob = await exportPdf(auth.token!, props.draft, props.settings, props.fullName)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'resume.pdf'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.preview-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #2a2a2a;
}

.preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: #1e1e1e;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}

.preview-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 24px 16px;
  display: flex;
  justify-content: center;
}

/* Wrapper sized to exactly A4 at 96dpi so the iframe and the
   page-limit-line overlay are in the same coordinate space.    */
.preview-frame-wrap {
  position: relative;
  width: v-bind('A4_W + "px"');
  flex-shrink: 0;
}

/* The iframe renders the backend HTML at 100% — no scaling.
   Height is auto so content taller than one A4 page shows correctly. */
.preview-iframe {
  width: v-bind('A4_W + "px"');
  height: v-bind('A4_H + "px"');
  border: none;
  display: block;
  background: #fff;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5);
}

/* Red dashed line at exactly 297mm (1122px at 96dpi).
   Content below this line will appear on page 2 of the PDF. */
.page-limit-line {
  position: absolute;
  left: 0;
  right: 0;
  top: v-bind('A4_H + "px"');
  height: 0;
  border-top: 1.5px dashed rgba(220, 80, 80, 0.6);
  pointer-events: none;
}
.page-limit-line::after {
  content: 'A4 page 1 limit';
  position: absolute;
  right: 4px;
  top: 2px;
  font-size: 9px;
  color: rgba(220, 80, 80, 0.6);
  white-space: nowrap;
}
</style>
