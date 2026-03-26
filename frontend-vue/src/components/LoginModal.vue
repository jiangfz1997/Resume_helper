<template>
  <n-modal
    :show="show"
    preset="card"
    title="Sign In"
    style="width: 420px"
    :mask-closable="true"
    @update:show="$emit('update:show', $event)"
  >
    <n-tabs v-model:value="tab" type="line" animated>
      <n-tab-pane name="login" tab="Login">
        <n-form
          ref="loginFormRef"
          :model="loginForm"
          :rules="loginRules"
          style="margin-top: 16px"
        >
          <n-form-item path="email" label="Email">
            <n-input v-model:value="loginForm.email" placeholder="you@example.com" />
          </n-form-item>
          <n-form-item path="password" label="Password">
            <n-input v-model:value="loginForm.password" type="password" placeholder="••••••••" />
          </n-form-item>
          <n-alert v-if="loginError" type="error" style="margin-bottom: 12px">
            {{ loginError }}
          </n-alert>
          <n-button type="primary" block :loading="loginLoading" @click="login">
            Login
          </n-button>
        </n-form>
      </n-tab-pane>

      <n-tab-pane name="register" tab="Register">
        <n-form
          ref="regFormRef"
          :model="regForm"
          :rules="regRules"
          style="margin-top: 16px"
        >
          <n-form-item path="full_name" label="Full Name">
            <n-input v-model:value="regForm.full_name" placeholder="Jane Doe" />
          </n-form-item>
          <n-form-item path="email" label="Email">
            <n-input v-model:value="regForm.email" placeholder="you@example.com" />
          </n-form-item>
          <n-form-item path="password" label="Password">
            <n-input
              v-model:value="regForm.password"
              type="password"
              placeholder="min 8 chars"
            />
          </n-form-item>
          <n-alert v-if="regError" type="error" style="margin-bottom: 12px">
            {{ regError }}
          </n-alert>
          <n-alert v-if="regSuccess" type="success" style="margin-bottom: 12px">
            {{ regSuccess }}
          </n-alert>
          <n-button type="primary" block :loading="regLoading" @click="register">
            Register
          </n-button>
        </n-form>
      </n-tab-pane>
    </n-tabs>
  </n-modal>
</template>

<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { loginUser, registerUser } from '../api/client'
import { useAuthStore } from '../stores/auth'

defineProps<{ show: boolean }>()
const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
}>()

const auth = useAuthStore()
const router = useRouter()
const tab = ref<'login' | 'register'>('login')

// login
const loginFormRef = ref<FormInst | null>(null)
const loginForm = ref({ email: '', password: '' })
const loginError = ref('')
const loginLoading = ref(false)

const loginRules: FormRules = {
  email: [{ required: true, message: 'Email is required', trigger: 'blur' }],
  password: [{ required: true, message: 'Password is required', trigger: 'blur' }],
}

async function login(): Promise<void> {
  await loginFormRef.value?.validate()
  loginError.value = ''
  loginLoading.value = true
  try {
    const { access_token } = await loginUser(loginForm.value.email, loginForm.value.password)
    auth.setToken(access_token)
    emit('update:show', false)
    router.push('/generate')
  } catch (e) {
    loginError.value = (e as Error).message
  } finally {
    loginLoading.value = false
  }
}

// register
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
    const user = await registerUser(regForm.value)
    regSuccess.value = `Account created for ${user.email}. You can now log in.`
    tab.value = 'login'
    loginForm.value.email = regForm.value.email
  } catch (e) {
    regError.value = (e as Error).message
  } finally {
    regLoading.value = false
  }
}
</script>
