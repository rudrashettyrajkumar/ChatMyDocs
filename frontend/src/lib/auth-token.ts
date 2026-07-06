/** The JWT is the single tenant credential now (the old anonymous session id is
 *  gone). Kept in localStorage so a refresh stays signed in; mirrored in a
 *  module variable so the API client reads it without a storage hit per call. */
const KEY = 'docchat_token'

let token: string | null = localStorage.getItem(KEY)
let onUnauthorized: (() => void) | null = null

export const getToken = (): string | null => token

export function setToken(value: string): void {
  token = value
  localStorage.setItem(KEY, value)
}

export function clearToken(): void {
  token = null
  localStorage.removeItem(KEY)
}

/** AuthContext registers a callback here so any 401 from the API (expired or
 *  revoked token) transparently logs the user out and bounces them to sign-in. */
export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn
}

export function handleUnauthorized(): void {
  clearToken()
  onUnauthorized?.()
}
