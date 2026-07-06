import { getToken } from '../lib/auth-token'
import type { ApiErrorBody, AuthResponse, AuthUser } from './types'
import { ApiError } from './types'

const API_URL = import.meta.env.VITE_API_URL as string

async function parse<T>(res: Response): Promise<T> {
  if (res.ok) return res.json() as Promise<T>
  let body: ApiErrorBody
  try {
    body = await res.json()
  } catch {
    body = { error: 'unknown', detail: `Request failed (${res.status})` }
  }
  throw new ApiError(body, res.status)
}

export function register(email: string, password: string, name?: string): Promise<AuthResponse> {
  return fetch(`${API_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: name || null }),
  }).then((r) => parse<AuthResponse>(r))
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  }).then((r) => parse<AuthResponse>(r))
}

export function fetchMe(): Promise<AuthUser> {
  return fetch(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  }).then((r) => parse<AuthUser>(r))
}
