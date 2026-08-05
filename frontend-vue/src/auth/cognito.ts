import { cognitoConfig } from './config'

const VERIFIER_KEY = 'cognito:pkce-verifier'
const STATE_KEY = 'cognito:oauth-state'

interface TokenResponse {
  access_token: string
  expires_in: number
  id_token: string
  refresh_token?: string
  token_type: string
}

export async function startCognitoLogin(): Promise<void> {
  const config = cognitoConfig()
  const verifier = randomUrlSafe(64)
  const state = randomUrlSafe(32)
  sessionStorage.setItem(VERIFIER_KEY, verifier)
  sessionStorage.setItem(STATE_KEY, state)
  const parameters = new URLSearchParams({
    client_id: config.clientId,
    response_type: 'code',
    scope: 'openid email profile',
    redirect_uri: config.redirectUri,
    code_challenge_method: 'S256',
    code_challenge: await sha256UrlSafe(verifier),
    state,
  })
  window.location.assign(`${config.domain}/oauth2/authorize?${parameters.toString()}`)
}

export async function completeCognitoLogin(code: string, state: string): Promise<TokenResponse> {
  const config = cognitoConfig()
  const expectedState = sessionStorage.getItem(STATE_KEY)
  const verifier = sessionStorage.getItem(VERIFIER_KEY)
  sessionStorage.removeItem(STATE_KEY)
  sessionStorage.removeItem(VERIFIER_KEY)
  if (!expectedState || state !== expectedState || !verifier) {
    throw new Error('The login state is invalid or expired. Please sign in again.')
  }
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: config.clientId,
    code,
    redirect_uri: config.redirectUri,
    code_verifier: verifier,
  })
  const response = await fetch(`${config.domain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!response.ok) throw new Error('Cognito token exchange failed. Please sign in again.')
  return response.json() as Promise<TokenResponse>
}

export function startCognitoLogout(): void {
  const config = cognitoConfig()
  const parameters = new URLSearchParams({ client_id: config.clientId, logout_uri: config.logoutUri })
  window.location.assign(`${config.domain}/logout?${parameters.toString()}`)
}

function randomUrlSafe(length: number): string {
  return base64Url(crypto.getRandomValues(new Uint8Array(length)))
}

async function sha256UrlSafe(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return base64Url(new Uint8Array(digest))
}

function base64Url(bytes: Uint8Array): string {
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}
