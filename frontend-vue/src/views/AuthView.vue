<template>
  <n-card v-if="cognitoEnabled" title="Job Dashboard" style="max-width: 480px; margin: 60px auto">
    <n-space vertical size="large">
      <n-text depth="3">Sign in with one of the administrator-created accounts.</n-text>
      <n-button type="primary" block :loading="cognitoLoading" @click="loginWithCognito">Sign in</n-button>
    </n-space>
  </n-card>
  <n-card v-else title="Authentication" style="max-width: 480px; margin: 40px auto">
    <n-tabs v-model:value="tab" type="line" animated>
      <!-- Login -->
      <n-tab-pane name="login" tab="Login">
        <n-form ref="loginFormRef" :model="loginForm" :rules="loginRules" style="margin-top: 16px">
          <n-form-item path="email" label="Email">
            <n-input v-model:value="loginForm.email" placeholder="you@example.com" default-value="fj@uwo.ca" />
          </n-form-item>
          <n-form-item path="password" label="Password">
            <n-input v-model:value="loginForm.password" type="password" placeholder="••••••••" default-value="123123123123"/>
          </n-form-item>
          <n-alert v-if="loginError" type="error" style="margin-bottom: 12px">{{ loginError }}</n-alert>
          <n-button type="primary" block :loading="loginLoading" @click="login">Login</n-button>
        </n-form>
      </n-tab-pane>

      <!-- Register -->
      <n-tab-pane name="register" tab="Register">
        <n-form ref="regFormRef" :model="regForm" :rules="regRules" style="margin-top: 16px">
          <n-form-item path="full_name" label="Full Name">
            <n-input v-model:value="regForm.full_name" placeholder="Jane Doe" />
          </n-form-item>
          <n-form-item path="email" label="Email">
            <n-input v-model:value="regForm.email" placeholder="you@example.com" />
          </n-form-item>
          <n-form-item path="password" label="Password">
            <n-input v-model:value="regForm.password" type="password" placeholder="min 8 chars" />
          </n-form-item>
          <n-alert v-if="regError" type="error" style="margin-bottom: 12px">{{ regError }}</n-alert>
          <n-alert v-if="regSuccess" type="success" style="margin-bottom: 12px">{{ regSuccess }}</n-alert>
          <n-button type="primary" block :loading="regLoading" @click="register">Register</n-button>
        </n-form>
      </n-tab-pane>
    </n-tabs>
  </n-card>
</template>

<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { loginUser, registerUser } from '../api/client'
import { startCognitoLogin } from '../auth/cognito'
import { authMode } from '../auth/config'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

onMounted(() => {
  if (auth.isAuthenticated) router.replace(authMode === 'cognito' ? '/jobs' : '/generate')
})

const cognitoEnabled = authMode === 'cognito'
const cognitoLoading = ref(false)

async function loginWithCognito(): Promise<void> {
  cognitoLoading.value = true
  try {
    await startCognitoLogin()
  } finally {
    cognitoLoading.value = false
  }
}

const tab = ref<'login' | 'register'>('login')

// ── login ──────────────────────────────────────────────────────
const loginFormRef = ref<FormInst | null>(null)
// const loginForm = ref({ email: '', password: '' })


// For debug use
const loginForm = ref({ email: 'fj@uwo.ca', password: '123123123123' })


const loginError = ref('')
const loginLoading = ref(false)

const loginRules: FormRules = {
  email: [{ required: true, message: 'Email is required', trigger: 'blur'  }],
  password: [{ required: true, message: 'Password is required', trigger: 'blur' }],
}

async function login(): Promise<void> {
  await loginFormRef.value?.validate()
  loginError.value = ''
  loginLoading.value = true
  try {
    // console.log("Try login with: ", loginForm.value)
    const { access_token } = await loginUser(loginForm.value.email, loginForm.value.password)

    auth.setToken(access_token)
    console.log("Login successful, token stored.")

    router.push('/generate')

  } catch (e) {
    loginError.value = (e as Error).message
    console.error("Login failed: ", loginError.value)
    console.error(e)
  } finally {
    loginLoading.value = false
  }
}

// ── register ───────────────────────────────────────────────────
const regFormRef = ref<FormInst | null>(null)
const regForm = ref({ full_name: '', email: '', password: '' })
const regError = ref('')
const regSuccess = ref('')
const regLoading = ref(false)

const regRules: FormRules = {
  full_name: [{ required: true, message: 'Full name is required', trigger: 'blur' }],
  email: [{ required: true, message: 'Email is required', trigger: 'blur' }],
  password: [{ required: true, min: 8, message: 'Min 8 characters', trigger: 'blur' }],
}

async function register(): Promise<void> {
  await regFormRef.value?.validate()

  regError.value = ''
  regSuccess.value = ''


  regLoading.value = true
  try {
    console.log("Try register with: ", regForm.value)
    const user = await registerUser(regForm.value)
    // console.log("regis user info: ", user)
    // console.log("???????")

    regSuccess.value = `Account created for ${user.email}. You can now log in.`

    tab.value = 'login'
    loginForm.value.email = regForm.value.email
  } catch (e) {
    regError.value = (e as Error).message
    console.error("Registration failed: ", regError.value)
    console.error(e)
  } finally {
    regLoading.value = false
  }
}
</script>
