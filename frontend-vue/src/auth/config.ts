export type AuthMode = 'disabled' | 'cognito' | 'legacy'

export const authMode: AuthMode = import.meta.env.VITE_AUTH_MODE ?? 'disabled'

export interface CognitoConfig {
  domain: string
  clientId: string
  redirectUri: string
  logoutUri: string
}

export function cognitoConfig(): CognitoConfig {
  return {
    domain: required('VITE_COGNITO_DOMAIN', import.meta.env.VITE_COGNITO_DOMAIN).replace(/\/$/, ''),
    clientId: required('VITE_COGNITO_CLIENT_ID', import.meta.env.VITE_COGNITO_CLIENT_ID),
    redirectUri: required('VITE_COGNITO_REDIRECT_URI', import.meta.env.VITE_COGNITO_REDIRECT_URI),
    logoutUri: required('VITE_COGNITO_LOGOUT_URI', import.meta.env.VITE_COGNITO_LOGOUT_URI),
  }
}

function required(name: string, value: string | undefined): string {
  if (!value) throw new Error(`${name} is required when VITE_AUTH_MODE=cognito`)
  return value
}
