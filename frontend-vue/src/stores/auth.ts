import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

function isExpired(t: string): boolean {
  try {
    const payload = JSON.parse(atob(t.split('.')[1]))
    return typeof payload.exp === 'number' && payload.exp * 1000 < Date.now()
  } catch {
    return true
  }
}

export const useAuthStore = defineStore('auth', () => {
  const raw = localStorage.getItem('token')
  const token = ref<string | null>(raw && !isExpired(raw) ? raw : null)
  if (!token.value) localStorage.removeItem('token')

  const isAuthenticated = computed(() => token.value !== null)

  function setToken(t: string): void {
    token.value = t
    localStorage.setItem('token', t)
  }

  function clearToken(): void {
    token.value = null
    localStorage.removeItem('token')
  }

  return { token, isAuthenticated, setToken, clearToken }
})
