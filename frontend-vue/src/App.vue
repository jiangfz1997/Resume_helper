<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides">
    <n-global-style />
    <n-message-provider>
      <n-layout style="min-height: 100vh">
        <n-layout-header
          bordered
          style="padding: 0 24px; display: flex; align-items: center; gap: 32px; height: 56px"
        >
          <span
            style="
              font-family: monospace;
              font-size: 15px;
              color: #7eb8f7;
              white-space: nowrap;
              cursor: pointer;
            "
            @click="router.push(authMode === 'cognito' ? '/jobs' : auth.isAuthenticated ? '/generate' : '/jobs')"
          >
            Resume Tailoring Assistant
          </span>

          <n-menu
            v-if="auth.isAuthenticated || route.path === '/jobs'"
            :value="activeKey"
            mode="horizontal"
            :options="visibleMenuOptions"
            style="flex: 1"
            @update:value="onNav"
          />
          <div v-else style="flex: 1" />

          <template v-if="auth.isAuthenticated">
            <n-button size="small" quaternary @click="logout">Logout</n-button>
          </template>
          <template v-else>
            <n-button size="small" type="primary" @click="signIn">Sign In</n-button>
          </template>
        </n-layout-header>

        <n-layout-content :style="contentStyle">
          <router-view />
        </n-layout-content>
      </n-layout>

      <LoginModal v-model:show="showLogin" />
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { darkTheme, NGlobalStyle } from 'naive-ui'
import type { GlobalThemeOverrides, MenuOption } from 'naive-ui'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { startCognitoLogout } from './auth/cognito'
import { authMode } from './auth/config'
import { useAuthStore } from './stores/auth'
import LoginModal from './components/LoginModal.vue'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const activeKey = computed(() => route.path)

const contentStyle = computed(() => {
  if (route.path === '/generate' || route.path === '/jobs' || route.path === '/job-settings') {
    return { padding: '0', maxWidth: '100%', margin: '0', overflow: 'hidden', height: 'calc(100vh - 56px)' }
  }
  return { padding: '24px', maxWidth: '960px', margin: '0 auto' }
})
const showLogin = ref(false)

const menuOptions: MenuOption[] = [
  { label: 'Jobs', key: '/jobs' },
  { label: 'Applications', key: '/applications' },
  { label: 'Job Settings', key: '/job-settings' },
  { label: 'Generate', key: '/generate' },
  { label: 'Profile', key: '/profile' },
  { label: 'Sessions', key: '/sessions' },
  // DEPRECATED: Templates feature hidden until LaTeX template workflow is redesigned
  // { label: 'Templates', key: '/templates' },
]

const visibleMenuOptions = computed(() => authMode === 'cognito' ? menuOptions.slice(0, 3) : auth.isAuthenticated ? menuOptions : menuOptions.slice(0, 1))

const themeOverrides: GlobalThemeOverrides = {
  common: { fontFamilyMono: 'monospace' },
}

function onNav(key: string): void {
  router.push(key)
}

function logout(): void {
  auth.clearToken()
  if (authMode === 'cognito') {
    startCognitoLogout()
    return
  }
  router.push('/auth')
}

function signIn(): void {
  if (authMode === 'cognito') {
    router.push('/auth')
    return
  }
  showLogin.value = true
}
</script>
