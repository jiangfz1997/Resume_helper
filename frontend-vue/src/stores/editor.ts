import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useEditorStore = defineStore('editor', () => {
  const latexContent = ref('')

  function setContent(content: string): void {
    latexContent.value = content
  }

  function clear(): void {
    latexContent.value = ''
  }

  return { latexContent, setContent, clear }
})
