<template>
  <!-- Floating chat window -->
  <div v-if="isOpen" class="chat-window">
    <div class="chat-header">
      <span class="chat-title">Resume Assistant</span>
      <button class="header-close" @click="isOpen = false">&#x2715;</button>
    </div>

    <div class="chat-messages" ref="messagesEl">
      <div v-if="messages.length === 0" class="chat-empty">
        Ask me anything, or click <strong>Comment</strong> on a section for targeted edits.
      </div>
      <div
        v-for="(msg, idx) in messages"
        :key="msg.id ?? idx"
        class="chat-bubble-wrap"
        :class="msg.role"
      >
        <div v-if="msg.scope" class="scope-tag">@ {{ msg.scope.label }}</div>
        <div class="chat-bubble">{{ msg.content }}</div>
        <div v-if="msg.patch" class="patch-card">
          <div class="patch-card-label">Suggested change</div>
          <div class="patch-card-summary">{{ msg.patch.diff_summary }}</div>
          <div class="patch-card-actions">
            <button class="btn-apply" @click="applyPatch(msg.patch!)">Apply</button>
            <button class="btn-dismiss" @click="msg.patch = undefined">Dismiss</button>
          </div>
        </div>
      </div>
      <div v-if="loading" class="chat-bubble-wrap assistant">
        <div class="chat-bubble typing">Thinking...</div>
      </div>
    </div>

    <div v-if="pendingScope" class="scope-bar">
      <span class="scope-bar-text">@ {{ pendingScope.label }}</span>
      <button class="scope-bar-clear" @click="pendingScope = null">&#x2715;</button>
    </div>

    <div class="chat-footer">
      <textarea
        v-model="inputText"
        class="chat-input"
        placeholder="Type your message..."
        rows="2"
        @keydown.enter.exact.prevent="submit"
      />
      <button class="btn-send" :disabled="loading || !inputText.trim()" @click="submit">
        &#x27A4;
      </button>
    </div>
  </div>

  <!-- FAB trigger button -->
  <button class="chat-fab" @click="isOpen = !isOpen" :class="{ open: isOpen }">
    <span v-if="!isOpen" class="fab-icon">&#x1F4AC;</span>
    <span v-else class="fab-icon">&#x2715;</span>
  </button>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useAuthStore } from '../stores/auth'
import { streamChatMessage, getChatHistory } from '../api/client'
import type { ChatMessage, ChatScope, ResumePatch, TailoredResumeDraft } from '../api/client'

const props = defineProps<{
  sessionId: string
  draft: TailoredResumeDraft
  pendingScopeInit?: ChatScope
}>()

const emit = defineEmits<{
  (e: 'patch', patch: ResumePatch): void
}>()

const auth = useAuthStore()
const isOpen = ref(false)
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const loading = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const pendingScope = ref<ChatScope | null>(null)

watch(
  () => props.pendingScopeInit,
  (v) => {
    if (v) {
      pendingScope.value = v
      isOpen.value = true
    }
  },
)

async function loadHistory() {
  if (!auth.token) return
  try {
    messages.value = await getChatHistory(props.sessionId, auth.token)
  } catch {
    // non-fatal
  }
}

loadHistory()

async function submit() {
  const text = inputText.value.trim()
  if (!text || loading.value || !auth.token) return

  const userMsg: ChatMessage = {
    role: 'user',
    content: text,
    scope: pendingScope.value ?? undefined,
    created_at: new Date().toISOString(),
  }
  messages.value.push(userMsg)
  inputText.value = ''
  loading.value = true
  await scrollBottom()

  // placeholder bubble that gets filled token by token
  const assistantMsg: ChatMessage = { role: 'assistant', content: '' }
  messages.value.push(assistantMsg)

  try {
    // Deep-clone draft to strip Vue reactivity proxies before serialising.
    // History only needs role/content/scope for LLM context — strip patch to
    // avoid serialisation issues with complex updated_value objects.
    const plainDraft = JSON.parse(JSON.stringify(props.draft))
    const plainHistory = messages.value.slice(0, -2).map((m) => ({
      role: m.role,
      content: m.content,
      ...(m.scope ? { scope: m.scope } : {}),
    }))

    const stream = streamChatMessage(
      {
        session_id: props.sessionId,
        draft: plainDraft,
        message: text,
        scope: pendingScope.value ?? undefined,
        history: plainHistory,
      },
      auth.token,
    )

    for await (const event of stream) {
      if (event.type === 'token') {
        assistantMsg.content += event.content
        await scrollBottom()
      } else if (event.type === 'patch') {
        assistantMsg.patch = {
          path: event.path,
          updated_value: event.updated_value,
          diff_summary: event.diff_summary,
        }
      }
    }

    pendingScope.value = null
  } catch (err: unknown) {
    assistantMsg.content = `Error: ${err instanceof Error ? err.message : 'Unknown error'}`
  } finally {
    loading.value = false
    await scrollBottom()
  }
}

function applyPatch(patch: ResumePatch) {
  emit('patch', patch)
}

async function scrollBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

defineExpose({
  setScope(s: ChatScope) {
    pendingScope.value = s
    isOpen.value = true
  },
  prefill(text: string) {
    inputText.value = text
    isOpen.value = true
  },
})
</script>

<style scoped>
/* FAB button */
.chat-fab {
  position: fixed;
  bottom: 28px;
  right: 28px;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: #1890ff;
  color: #fff;
  border: none;
  cursor: pointer;
  z-index: 1000;
  box-shadow: 0 4px 16px rgba(24, 144, 255, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s, transform 0.2s;
}

.chat-fab:hover {
  background: #096dd9;
  transform: scale(1.07);
}

.chat-fab.open {
  background: #595959;
}

.fab-icon {
  font-size: 22px;
  line-height: 1;
}

/* Floating chat window */
.chat-window {
  position: fixed;
  bottom: 94px;
  right: 28px;
  width: 360px;
  height: 500px;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.18);
  z-index: 999;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  font-size: 14px;
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: #1890ff;
  color: #fff;
  flex-shrink: 0;
}

.chat-title {
  font-weight: 600;
  font-size: 15px;
}

.header-close {
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0;
}

.header-close:hover {
  color: #fff;
}

/* Messages */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 14px 14px 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chat-empty {
  color: #aaa;
  text-align: center;
  margin: auto;
  line-height: 1.6;
  font-size: 13px;
}

.chat-bubble-wrap {
  display: flex;
  flex-direction: column;
  max-width: 88%;
}

.chat-bubble-wrap.user {
  align-self: flex-end;
  align-items: flex-end;
}

.chat-bubble-wrap.assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.scope-tag {
  font-size: 11px;
  color: #1890ff;
  font-weight: 600;
  margin-bottom: 3px;
  padding: 0 2px;
}

.chat-bubble {
  padding: 8px 12px;
  border-radius: 12px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}

.chat-bubble-wrap.user .chat-bubble {
  background: #1890ff;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.chat-bubble-wrap.assistant .chat-bubble {
  background: #f0f0f0;
  color: #222;
  border-bottom-left-radius: 4px;
}

.typing {
  color: #999;
  font-style: italic;
}

/* Patch card */
.patch-card {
  margin-top: 6px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
}

.patch-card-label {
  font-weight: 600;
  color: #52c41a;
  margin-bottom: 4px;
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.4px;
}

.patch-card-summary {
  color: #444;
  margin-bottom: 8px;
  line-height: 1.4;
}

.patch-card-actions {
  display: flex;
  gap: 8px;
}

.btn-apply {
  padding: 3px 12px;
  background: #52c41a;
  color: #fff;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 12px;
}

.btn-dismiss {
  padding: 3px 12px;
  background: none;
  border: 1px solid #d9d9d9;
  border-radius: 5px;
  cursor: pointer;
  font-size: 12px;
  color: #666;
}

/* Scope bar */
.scope-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 14px;
  background: #e6f7ff;
  border-top: 1px solid #bae7ff;
  flex-shrink: 0;
  font-size: 12px;
}

.scope-bar-text {
  color: #1890ff;
  font-weight: 500;
}

.scope-bar-clear {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}

/* Input area */
.chat-footer {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
  background: #fafafa;
}

.chat-input {
  flex: 1;
  resize: none;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 13px;
  line-height: 1.4;
  outline: none;
  background: #fff;
}

.chat-input:focus {
  border-color: #1890ff;
}

.btn-send {
  width: 36px;
  height: 36px;
  align-self: flex-end;
  background: #1890ff;
  color: #fff;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.btn-send:disabled {
  background: #d9d9d9;
  cursor: not-allowed;
}
</style>
