import React, { useEffect, useState } from 'react'
import { useAuth } from './hooks/useAuth'
import { consumePendingMessage } from './utils/session'
import ChatWindow from './components/ChatWindow'

const SunIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="5"></circle>
    <line x1="12" y1="1" x2="12" y2="3"></line>
    <line x1="12" y1="21" x2="12" y2="23"></line>
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
    <line x1="1" y1="12" x2="3" y2="12"></line>
    <line x1="21" y1="12" x2="23" y2="12"></line>
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
  </svg>
)

const MoonIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
  </svg>
)

export default function App() {
  const { user, isLoggedIn, credExpiring, isLoading, login, logout } = useAuth()
  
  // Theme state: default to 'light'
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('app-theme')
    return saved ? saved : 'light'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('app-theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme(t => t === 'light' ? 'dark' : 'light')
  }

  // After OIDC redirect, auto-resume the pending message
  // This is handled inside ChatWindow via the ?msg= URL param + sessionStorage
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.has('resumed')) {
      const clean = new URL(window.location.href)
      clean.searchParams.delete('resumed')
      window.history.replaceState({}, '', clean.toString())
    }
  }, [])

  return (
    <div className="app-shell">
      <div className="chat-shell" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* ── Header ─────────────────────────────────────────────────── */}
        <header className="header">
          <div className="header-brand">
            <div className="header-logo" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 17L12 22L22 17" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 12L12 17L22 12" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div>
              <div className="header-title">AWS Enterprise Assistant</div>
            </div>
          </div>

          <div className="header-actions">
            {credExpiring && (
              <span
                title="AWS credentials expiring soon — they will refresh automatically on your next query"
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--aws-orange)',
                  background: 'var(--aws-orange-dim)',
                  padding: '6px 12px',
                  borderRadius: 'var(--radius-pill)',
                  border: '1px solid rgba(255, 153, 0, 0.3)',
                  cursor: 'default',
                  boxShadow: '0 0 10px rgba(255,153,0,0.1)'
                }}
              >
                ⚠️ Creds expiring
              </span>
            )}

            <button
              className="theme-toggle-btn"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
              title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
            >
              {theme === 'light' ? <MoonIcon /> : <SunIcon />}
            </button>

            {isLoggedIn ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div className="user-badge" aria-label={`Logged in as ${user?.email || user?.user_id}`}>
                  <span className="user-badge-dot" title="Session active" />
                  <span>{user?.email || user?.user_id || 'AWS Admin'}</span>
                </div>
                <button
                  id="header-logout-btn"
                  className="btn btn-ghost"
                  onClick={logout}
                  aria-label="Sign out"
                >
                  Sign Out
                </button>
              </div>
            ) : (
              !isLoading && (
                <div className="user-badge" aria-label="Not signed in">
                  <span className="user-badge-dot offline" />
                  <span>Not signed in</span>
                </div>
              )
            )}
          </div>
        </header>

        {/* ── Credential expiry notification bar ─────────────────────── */}
        {credExpiring && (
          <div className="cred-expiry-banner" role="status">
            ⏱ Your AWS session expires soon. It will refresh automatically on your next request.
          </div>
        )}

        {/* ── Chat area ──────────────────────────────────────────────── */}
        <ChatWindow
          isLoggedIn={isLoggedIn}
          onLogin={login}
        />
      </div>
    </div>
  )
}
