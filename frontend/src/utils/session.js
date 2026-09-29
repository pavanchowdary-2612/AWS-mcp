/**
 * sessionStorage helpers for the lazy-auth resume flow.
 *
 * When the agent signals AUTH_REQUIRED, the frontend:
 *   1. Saves the user's message via savePendingMessage()
 *   2. Redirects to /auth/login?msg=<encoded>
 *   3. After login, the backend embeds the message in the redirect URL.
 *   4. The frontend reads it via consumePendingMessage() and auto-submits.
 *
 * We use both sessionStorage (browser-side) AND the server-side ?msg param
 * from the backend redirect as two independent recovery paths.
 */

const KEY = 'aws_chatbot_pending_msg'

/**
 * Save a message to sessionStorage before triggering an auth redirect.
 * @param {string} message
 */
export function savePendingMessage(message) {
  try {
    sessionStorage.setItem(KEY, message)
  } catch {
    // sessionStorage may be blocked in certain iframe contexts
  }
}

/**
 * Read and clear the pending message from sessionStorage.
 * Also checks the ?msg= URL query param (set by the backend after login).
 * Returns null if nothing is pending.
 *
 * @returns {string|null}
 */
export function consumePendingMessage() {
  // 1. Check URL param first (authoritative — set by server after IdP redirect)
  const params = new URLSearchParams(window.location.search)
  const fromUrl = params.get('msg')
  if (fromUrl) {
    // Clean the URL without reloading
    const clean = new URL(window.location.href)
    clean.searchParams.delete('msg')
    clean.searchParams.delete('resumed')
    window.history.replaceState({}, '', clean.toString())
    return fromUrl
  }

  // 2. Fallback: sessionStorage
  try {
    const stored = sessionStorage.getItem(KEY)
    if (stored) {
      sessionStorage.removeItem(KEY)
      return stored
    }
  } catch {
    // ignore
  }

  return null
}

/**
 * Build the login URL, embedding the pending message so it survives the redirect.
 * @param {string} pendingMessage
 * @returns {string}
 */
export function buildLoginUrl(pendingMessage = '') {
  const base = '/auth/login'
  if (!pendingMessage) return base
  return `${base}?msg=${encodeURIComponent(pendingMessage)}`
}
