import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Lock, Mail, User } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/types'
import { AuthScaffold } from './AuthScaffold'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'

export function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setFieldError(null)
    if (password.length < 8) {
      setFieldError('Use at least 8 characters.')
      return
    }
    setLoading(true)
    try {
      await register(email, password, name)
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthScaffold
      title="Create your account"
      subtitle="Free to start — no credit card, no setup."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-brand hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && (
          <div
            role="alert"
            className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
          >
            {error}
          </div>
        )}
        <Input
          label="Name"
          autoComplete="name"
          placeholder="Ada Lovelace"
          icon={<User className="size-5" />}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          icon={<Mail className="size-5" />}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          placeholder="At least 8 characters"
          icon={<Lock className="size-5" />}
          hint="At least 8 characters."
          error={fieldError ?? undefined}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button type="submit" size="lg" loading={loading} className="mt-2 w-full">
          Create account
        </Button>
      </form>
    </AuthScaffold>
  )
}
