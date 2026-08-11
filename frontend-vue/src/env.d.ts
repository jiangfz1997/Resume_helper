/// <reference types="vite/client" />

declare module '*.csv?raw' {
  const content: string
  export default content
}

interface ImportMetaEnv {
  readonly VITE_JOB_DATA_SOURCE?: 'mock' | 'api'
  readonly VITE_JOBS_API_URL?: string
  readonly VITE_APPLICATIONS_API_URL?: string
  readonly VITE_AUTH_MODE?: 'disabled' | 'cognito' | 'legacy'
  readonly VITE_COGNITO_DOMAIN?: string
  readonly VITE_COGNITO_CLIENT_ID?: string
  readonly VITE_COGNITO_REDIRECT_URI?: string
  readonly VITE_COGNITO_LOGOUT_URI?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
