import { useState, useRef, useCallback } from 'react'
import { savePendingMessage } from '../utils/session'

/**
 * useChat — manages conversation state and the streaming SSE connection.
 *
 * Message shape:
 *   { id, role: 'user'|'assistant'|'tool'|'error', content, tools?, timestamp }
 *
 * Streaming events from the backend:
 *   delta             — partial text chunk
 *   tool_start        — tool call initiated
 *   tool_result       — tool call completed
 *   needs_confirmation — write action pending user approval
 *   error             — agent error (AUTH_REQUIRED | PERMISSION_DENIED | AGENT_ERROR)
 *   done              — stream ended
 */
export function useChat({ onAuthRequired, onNeedsConfirmation }) {
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  // Tracks tool call cards keyed by tool name
  const [activeTools, setActiveTools] = useState({})
  const abortRef = useRef(null)
  const currentMsgIdRef = useRef(null)

  // ── Helpers ───────────────────────────────────────────────────────────────

  const addMessage = useCallback((msg) => {
    setMessages(prev => [...prev, { id: Date.now() + Math.random(), timestamp: new Date(), ...msg }])
  }, [])

  const appendToLastAssistant = useCallback((text) => {
    setMessages(prev => {
      const copy = [...prev]
      const last = copy[copy.length - 1]
      if (last && last.role === 'assistant') {
        copy[copy.length - 1] = { ...last, content: last.content + text }
      } else {
        copy.push({
          id: Date.now() + Math.random(),
          role: 'assistant',
          content: text,
          timestamp: new Date(),
          tools: [],
        })
      }
      return copy
    })
  }, [])

  const updateToolInLastAssistant = useCallback((toolName, update) => {
    setMessages(prev => {
      const copy = [...prev]
      const last = copy[copy.length - 1]
      if (last && last.role === 'assistant') {
        const tools = last.tools || []
        const idx = tools.findIndex(t => t.name === toolName)
        if (idx >= 0) {
          const updated = [...tools]
          updated[idx] = { ...updated[idx], ...update }
          copy[copy.length - 1] = { ...last, tools: updated }
        } else {
          copy[copy.length - 1] = { ...last, tools: [...tools, { name: toolName, ...update }] }
        }
      }
      return copy
    })
  }, [])

  // ── Build Anthropic-formatted history for /chat ───────────────────────────

  const buildHistory = useCallback((msgs) => {
    return msgs
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({ role: m.role, content: m.content }))
  }, [])

  // ── Send a message ─────────────────────────────────────────────────────────

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isStreaming) return

    // Add user message to UI
    addMessage({ role: 'user', content: text })

    // Prepare assistant message placeholder
    setMessages(prev => [
      ...prev,
      { id: Date.now() + Math.random(), role: 'assistant', content: '', tools: [], timestamp: new Date() },
    ])
    setIsStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const history = buildHistory(messages)
      const resp = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ message: text, history }),
        signal: controller.signal,
      })

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`)
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw) continue

          let event
          try { event = JSON.parse(raw) } catch { continue }

          switch (event.type) {
            case 'delta':
              appendToLastAssistant(event.text)
              break

            case 'tool_start':
              updateToolInLastAssistant(event.tool, {
                name: event.tool,
                args: event.args,
                status: 'running',
              })
              break

            case 'tool_result':
              updateToolInLastAssistant(event.tool, {
                result: event.content,
                status: 'done',
              })
              break

            case 'needs_confirmation':
              setIsStreaming(false)
              onNeedsConfirmation?.({
                tool: event.tool,
                args: event.args,
                confirmToken: event.confirm_token,
              })
              break

            case 'error':
              if (event.code === 'AUTH_REQUIRED') {
                savePendingMessage(text)
                onAuthRequired?.(text)
              } else {
                // Replace last assistant placeholder with error
                setMessages(prev => {
                  const copy = [...prev]
                  const last = copy[copy.length - 1]
                  if (last?.role === 'assistant' && !last.content) {
                    copy[copy.length - 1] = {
                      ...last,
                      role: 'error',
                      content: event.message,
                      code: event.code,
                    }
                  } else {
                    copy.push({
                      id: Date.now(),
                      role: 'error',
                      content: event.message,
                      code: event.code,
                      timestamp: new Date(),
                    })
                  }
                  return copy
                })
              }
              setIsStreaming(false)
              break

            case 'done':
              setIsStreaming(false)
              break

            default:
              break
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setMessages(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last?.role === 'assistant' && !last.content) {
            copy[copy.length - 1] = { ...last, role: 'error', content: 'Connection error. Please try again.' }
          }
          return copy
        })
      }
      setIsStreaming(false)
    }
  }, [isStreaming, messages, buildHistory, addMessage, appendToLastAssistant, updateToolInLastAssistant, onAuthRequired, onNeedsConfirmation])

  // ── Submit confirmed write action ─────────────────────────────────────────

  const confirmAction = useCallback(async (confirmToken) => {
    setIsStreaming(true)
    setMessages(prev => [
      ...prev,
      { id: Date.now() + Math.random(), role: 'assistant', content: '', tools: [], timestamp: new Date() },
    ])

    try {
      const resp = await fetch('/chat/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ confirm_token: confirmToken, agent_state_key: '' }),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          let event
          try { event = JSON.parse(raw) } catch { continue }

          if (event.type === 'delta') appendToLastAssistant(event.text)
          else if (event.type === 'tool_result') {
            updateToolInLastAssistant(event.tool, { result: event.content, status: 'done' })
          }
          else if (event.type === 'done') setIsStreaming(false)
          else if (event.type === 'error') {
            setMessages(prev => [...prev, {
              id: Date.now(), role: 'error', content: event.message, timestamp: new Date(),
            }])
            setIsStreaming(false)
          }
        }
      }
    } catch {
      setIsStreaming(false)
    }
  }, [appendToLastAssistant, updateToolInLastAssistant])

  const cancelAction = useCallback(async (confirmToken) => {
    try {
      await fetch('/chat/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ confirm_token: confirmToken, agent_state_key: '' }),
      })
    } catch { /* best effort */ }
    addMessage({ role: 'assistant', content: '✋ Action cancelled.' })
  }, [addMessage])

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
  }, [])

  return {
    messages,
    isStreaming,
    sendMessage,
    confirmAction,
    cancelAction,
    stopStreaming,
    clearMessages,
  }
}
