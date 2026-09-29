import { useState, useEffect, useCallback } from 'react'

const AUTH_POLL_INTERVAL = 60_000 // 1 min — refresh session state from /auth/me

/**
 * useAuth — tracks the user's authentication state by polling /auth/me.
 *
 * Returns:
 *   user          — { user_id, email, groups, cred_expiry, has_aws_creds } | null
 *   isLoggedIn    — boolean
 *   credExpiring  — boolean (true when < 5 min remain on AWS creds)
 *   isLoading     — boolean (initial fetch in progress)
 *   login(msg?)   — redirect to /auth/login (preserving pending message)
 *   logout()      — POST /auth/logout, clear state
 *   refresh()     — manually re-fetch session state
 */
export function useAuth() {
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  const fetchMe = useCallback(async () => {
    try {
      const resp = await fetch('/auth/me', { credentials: 'include' })
      if (!resp.ok) { setUser(null); return }
      const data = await resp.json()
      if (data.authenticated) {
        setUser(data)
      } else {
        setUser(null)
      }
    } catch {
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => { fetchMe() }, [fetchMe])

  // Periodic refresh
  useEffect(() => {
    const id = setInterval(fetchMe, AUTH_POLL_INTERVAL)
    return () => clearInterval(id)
  }, [fetchMe])

  // Credential expiry detection
  const credExpiring = (() => {
    if (!user?.cred_expiry) return false
    const expiry = new Date(user.cred_expiry)
    const secsLeft = (expiry - Date.now()) / 1000
    return secsLeft < 300
  })()

  const login = useCallback((pendingMessage = '') => {
    const url = pendingMessage
      ? `/auth/login?msg=${encodeURIComponent(pendingMessage)}`
      : '/auth/login'
    window.location.href = url
  }, [])

  const logout = useCallback(async () => {
    try {
      await fetch('/auth/logout', { method: 'POST', credentials: 'include' })
    } catch { /* best effort */ }
    setUser(null)
  }, [])

  return {
    user,
    isLoggedIn: !!user,
    credExpiring,
    isLoading,
    login,
    logout,
    refresh: fetchMe,
  }
}
