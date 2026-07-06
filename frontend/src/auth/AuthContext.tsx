import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import * as authApi from '../api/auth'
import type { AuthUser } from '../api/types'
import { clearToken, getToken, setToken, setUnauthorizedHandler } from '../lib/auth-token'

type AuthState = {
  user: AuthUser | null
  /** True until the initial token check resolves — gate the app on this so a
   *  logged-in refresh doesn't flash the landing page. */
  initializing: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, name?: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [initializing, setInitializing] = useState(true)

  const logout = useCallback(() => {
    clearToken()
    setUser(null)
  }, [])

  // Any 401 anywhere (expired token) drops us back to signed-out.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
  }, [])

  // On boot, if we hold a token, validate it by loading the profile.
  useEffect(() => {
    if (!getToken()) {
      setInitializing(false)
      return
    }
    authApi
      .fetchMe()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setInitializing(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login(email, password)
    setToken(res.access_token)
    setUser(res.user)
  }, [])

  const register = useCallback(async (email: string, password: string, name?: string) => {
    const res = await authApi.register(email, password, name)
    setToken(res.access_token)
    setUser(res.user)
  }, [])

  return (
    <Ctx.Provider value={{ user, initializing, login, register, logout }}>{children}</Ctx.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
