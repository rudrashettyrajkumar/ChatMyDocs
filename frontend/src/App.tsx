import { Navigate, Route, Routes } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuth } from './auth/AuthContext'
import { Landing } from './pages/Landing'
import { Login } from './pages/Login'
import { Register } from './pages/Register'
import { Workspace } from './pages/Workspace'

function FullscreenLoader() {
  return (
    <div className="grid h-dvh place-items-center">
      <Loader2 className="size-7 animate-spin text-brand" aria-label="Loading" />
    </div>
  )
}

/** Gate for the app itself: wait out the boot token check, then require a user. */
function Protected({ children }: { children: React.ReactNode }) {
  const { user, initializing } = useAuth()
  if (initializing) return <FullscreenLoader />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** Keep already-signed-in users out of the marketing/auth pages. */
function PublicOnly({ children }: { children: React.ReactNode }) {
  const { user, initializing } = useAuth()
  if (initializing) return <FullscreenLoader />
  if (user) return <Navigate to="/app" replace />
  return <>{children}</>
}

function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <PublicOnly>
            <Landing />
          </PublicOnly>
        }
      />
      <Route
        path="/login"
        element={
          <PublicOnly>
            <Login />
          </PublicOnly>
        }
      />
      <Route
        path="/register"
        element={
          <PublicOnly>
            <Register />
          </PublicOnly>
        }
      />
      <Route
        path="/app"
        element={
          <Protected>
            <Workspace />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
