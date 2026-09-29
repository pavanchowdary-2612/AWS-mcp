import React from 'react'

/**
 * AuthGate — shown inline in the chat when authentication is needed.
 *
 * Props:
 *   onLogin(pendingMessage) — triggers OIDC redirect
 *   pendingMessage          — the message the user was trying to send
 */
export default function AuthGate({ onLogin, pendingMessage }) {
  return (
    <div className="auth-gate-banner" role="status" aria-label="Authentication required">
      <span style={{ fontSize: 22 }} aria-hidden="true">🔐</span>
      <div className="auth-gate-text">
        <strong>Sign in required</strong>
        <br />
        Accessing AWS resources requires authentication via IAM Identity Center.
        Your message will be automatically resumed after sign-in.
      </div>
      <button
        id="auth-gate-login-btn"
        className="btn btn-primary"
        onClick={() => onLogin(pendingMessage)}
        style={{ flexShrink: 0 }}
      >
        Sign In
      </button>
    </div>
  )
}
