<template>
  <div class="layout-panel">
    <!-- Font -->
    <div class="lp-section">
      <div class="lp-label">Font Family</div>
      <n-select
        v-model:value="s.font_family"
        :options="fontOptions"
        size="small"
        @update:value="notify"
      />
    </div>

    <div class="lp-section">
      <div class="lp-label">Font Size <span class="lp-hint">{{ s.font_size }}/5</span></div>
      <n-slider v-model:value="s.font_size" :min="1" :max="5" :step="1" @update:value="notify" />
    </div>

    <!-- Spacing -->
    <div class="lp-section">
      <div class="lp-label">Section Gap <span class="lp-hint">{{ s.section_gap }}/5</span></div>
      <n-slider v-model:value="s.section_gap" :min="1" :max="5" :step="1" @update:value="notify" />
    </div>

    <div class="lp-section">
      <div class="lp-label">Item Gap <span class="lp-hint">{{ s.item_gap }}/5</span></div>
      <n-slider v-model:value="s.item_gap" :min="1" :max="5" :step="1" @update:value="notify" />
    </div>

    <div class="lp-section">
      <div class="lp-label">Line Height <span class="lp-hint">{{ s.line_height }}/5</span></div>
      <n-slider v-model:value="s.line_height" :min="1" :max="5" :step="1" @update:value="notify" />
    </div>

    <!-- Margins -->
    <div class="lp-section">
      <div class="lp-label">Horizontal Margin <span class="lp-hint">{{ s.margin_h }}mm</span></div>
      <n-slider v-model:value="s.margin_h" :min="8" :max="25" :step="1" @update:value="notify" />
    </div>

    <div class="lp-section">
      <div class="lp-label">Vertical Margin <span class="lp-hint">{{ s.margin_v }}mm</span></div>
      <n-slider v-model:value="s.margin_v" :min="8" :max="25" :step="1" @update:value="notify" />
    </div>

    <!-- Accent color -->
    <div class="lp-section">
      <div class="lp-label">Accent Color</div>
      <n-space align="center" size="small">
        <input
          type="color"
          v-model="s.accent_color"
          class="color-input"
          @input="notify"
        />
        <n-text depth="3" style="font-size: 12px">{{ s.accent_color }}</n-text>
      </n-space>
    </div>

    <!-- Compact mode -->
    <div class="lp-section" style="flex-direction: row; align-items: center; justify-content: space-between">
      <div class="lp-label" style="margin-bottom: 0">Compact Mode</div>
      <n-switch v-model:value="s.compact_mode" size="small" @update:value="notify" />
    </div>

    <!-- Reset -->
    <n-button size="small" quaternary style="margin-top: 8px; width: 100%" @click="reset">
      Reset to defaults
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import type { LayoutSettings } from '../api/client'
import { defaultLayoutSettings } from '../api/client'

const props = defineProps<{ settings: LayoutSettings }>()
const emitEvent = defineEmits<{ (e: 'update:settings', v: LayoutSettings): void }>()

const s = reactive<LayoutSettings>({ ...props.settings })

function notify(): void {
  emitEvent('update:settings', { ...s })
}

function reset(): void {
  Object.assign(s, defaultLayoutSettings())
  emitEvent('update:settings', { ...s })
}

const fontOptions = [
  { label: 'Georgia', value: 'Georgia' },
  { label: 'Times New Roman', value: 'Times New Roman' },
  { label: 'Arial', value: 'Arial' },
  { label: 'Helvetica', value: 'Helvetica' },
  { label: 'Calibri', value: 'Calibri' },
  { label: 'Garamond', value: 'Garamond' },
]
</script>

<style scoped>
.layout-panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.lp-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 0;
  border-bottom: 1px solid #2a2a2a;
}
.lp-label {
  font-size: 12px;
  color: #aaa;
  display: flex;
  justify-content: space-between;
}
.lp-hint { color: #666; }
.color-input {
  width: 36px;
  height: 28px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  padding: 2px;
  background: transparent;
}
</style>
