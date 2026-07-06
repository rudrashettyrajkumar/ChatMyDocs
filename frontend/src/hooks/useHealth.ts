import { useEffect, useState } from 'react'
import { checkHealth } from '../api/client'

export type HealthState = 'checking' | 'ok' | 'degraded' | 'unreachable'

export function useHealth() {
  const [state, setState] = useState<HealthState>('checking')

  const check = () => {
    setState('checking')
    checkHealth()
      .then((res) => setState(res.status === 'ok' ? 'ok' : 'degraded'))
      .catch(() => setState('unreachable'))
  }

  useEffect(() => {
    check()
  }, [])

  return { state, recheck: check }
}
