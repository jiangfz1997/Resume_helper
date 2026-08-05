<template>
  <n-card title="Completing sign in" style="max-width: 480px; margin: 60px auto">
    <n-space vertical align="center">
      <n-spin v-if="!error" size="large" />
      <n-alert v-else type="error">{{ error }}</n-alert>
      <n-button v-if="error" type="primary" @click="router.replace('/auth')">Try again</n-button>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { completeCognitoLogin } from '../auth/cognito'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const error = ref('')

onMounted(async () => {
  const code = typeof route.query.code === 'string' ? route.query.code : ''
  const state = typeof route.query.state === 'string' ? route.query.state : ''
  const providerError = typeof route.query.error_description === 'string' ? route.query.error_description : ''
  if (providerError || !code || !state) {
    error.value = providerError || 'Cognito did not return a valid authorization code.'
    return
  }
  try {
    const tokens = await completeCognitoLogin(code, state)
    auth.setToken(tokens.access_token)
    await router.replace('/jobs')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'Sign in failed.'
  }
})
</script>
