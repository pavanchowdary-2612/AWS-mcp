import React, { useEffect, useRef, useState, useCallback } from 'react'
import MessageBubble from './MessageBubble'
import ThinkingIndicator from './ThinkingIndicator'
import AuthGate from './AuthGate'
import { useChat } from '../hooks/useChat'

const WELCOME_CHIPS = [
  '🔍 Why is my Lambda function failing?',
  '📊 Show CloudWatch metrics for my API Gateway',
  '🪣 List all S3 buckets in us-east-1',
  '💰 What are my top 5 cost drivers this month?',
  '🔐 Check IAM permissions for role dev-deployer',
  '🖥 List running EC2 instances',
  '📦 Show recent ECS task failures',
  '🗄 Check RDS slow query log',
]

/**
 * ChatWindow — full-height chat interface.
 *
 * Props:
 *   isLoggedIn  — boolean from useAuth
 *   onLogin     — function(pendingMessage?) to trigger OIDC redirect
 */
export default function ChatWindow({ isLoggedIn, onLogin }) {
  const [inputValue, setInputValue] = useState('')
  const [pendingAuthMessage, setPendingAuthMessage] = useState(null)
  const [pendingConfirmation, setPendingConfirmation] = useState(null)

  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  const handleAuthRequired = useCallback((msg) => {
    setPendingAuthMessage(msg)
  }, [])

  const handleNeedsConfirmation = useCallback((action) => {
    setPendingConfirmation(action)
  }, [])

  const { messages, isStreaming, sendMessage, confirmAction, cancelAction, clearMessages } = useChat({
    onAuthRequired: handleAuthRequired,
    onNeedsConfirmation: handleNeedsConfirmation,
  })

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  // Auto-resize textarea
  const handleTextareaChange = (e) => {
    setInputValue(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
  }

  const handleSend = () => {
    const text = inputValue.trim()
    if (!text || isStreaming) return
    setInputValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    setPendingAuthMessage(null)
    sendMessage(text)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleChipClick = (chip) => {
    // Strip emoji prefix
    const text = chip.replace(/^[\p{Emoji}\s]+/u, '').trim()
    setInputValue(text)
    textareaRef.current?.focus()
  }

  const handleConfirm = async (token) => {
    setPendingConfirmation(null)
    await confirmAction(token)
  }

  const handleCancel = (token) => {
    setPendingConfirmation(null)
    cancelAction(token)
  }

  const showWelcome = messages.length === 0 && !isStreaming

  return (
    <div className="chat-shell">
      {/* Messages area */}
      <div className="messages-scroll" id="chat-messages-scroll">
        <div className="messages-inner">
          {showWelcome ? (
            <div className="welcome-container">
              <div className="welcome-logo" aria-hidden="true">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 17L12 22L22 17" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 12L12 17L22 12" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <h1 className="welcome-title">AWS AI Assistant</h1>
              <p className="welcome-subtitle">
                Ask questions about your AWS infrastructure, diagnose issues, or take
                actions—all through natural language. Sign-in is only required when
                accessing live AWS data.
              </p>
              <div className="welcome-chips" role="list" aria-label="Suggested prompts">
                {WELCOME_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    className="welcome-chip"
                    role="listitem"
                    onClick={() => handleChipClick(chip)}
                    aria-label={`Suggested prompt: ${chip}`}
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg, idx) => {
                const isLast = idx === messages.length - 1;
                const isEmptyAssistant = msg.role === 'assistant' && !msg.content && (!msg.tools || msg.tools.length === 0);
                
                // If the assistant just started and has nothing to show yet, render the thinking indicator INSTEAD of an empty bubble
                if (isLast && isEmptyAssistant && isStreaming) {
                  return <ThinkingIndicator key={`thinking-${msg.id}`} />;
                }
                
                return <MessageBubble key={msg.id} message={msg} />;
              })}
              {pendingAuthMessage && (
                <AuthGate
                  onLogin={onLogin}
                  pendingMessage={pendingAuthMessage}
                />
              )}
            </>
          )}
          <div ref={messagesEndRef} aria-hidden="true" />
        </div>
      </div>

      {/* Input area */}
      <div className="input-area" role="region" aria-label="Message input">
        <div className="input-area-inner">
          <div className="input-row">
            <div className="chat-input-wrapper">
              <textarea
                ref={textareaRef}
                id="chat-input"
                className="chat-textarea"
                placeholder="Ask about your AWS resources… (Shift+Enter for newline)"
                value={inputValue}
                onChange={handleTextareaChange}
                onKeyDown={handleKeyDown}
                disabled={isStreaming}
                rows={1}
                aria-label="Chat message input"
                aria-multiline="true"
              />
              <button
                id="chat-send-btn"
                className="send-btn"
                onClick={handleSend}
                disabled={!inputValue.trim() || isStreaming}
                aria-label="Send message"
                title="Send (Enter)"
              >
                {isStreaming ? (
                  <span style={{ fontSize: 14 }}>⏹</span>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                  </svg>
                )}
              </button>
            </div>

            {messages.length > 0 && (
              <button
                className="btn btn-ghost btn-icon"
                onClick={clearMessages}
                title="New conversation"
                aria-label="Start new conversation"
                id="clear-chat-btn"
              >
                ✕
              </button>
            )}
          </div>

          {/* Hint chips — shown when input is empty */}
          {!inputValue && !isStreaming && messages.length > 0 && (
            <div className="input-hints" aria-label="Quick prompts">
              {WELCOME_CHIPS.slice(0, 3).map((chip) => (
                <button
                  key={chip}
                  className="hint-chip"
                  onClick={() => handleChipClick(chip)}
                  aria-label={`Quick prompt: ${chip}`}
                >
                  {chip}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Write-action confirmation modal (rendered via portal-like approach) */}
      {pendingConfirmation && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
          <div className="modal-card">
            <div className="modal-header">
              <div className="modal-danger-icon" aria-hidden="true">⚠️</div>
              <div>
                <div id="confirm-title" className="modal-title">Confirm Write Action</div>
                <div className="modal-subtitle">This action will make changes to your AWS environment</div>
              </div>
            </div>

            <div className="modal-tool-name">{pendingConfirmation.tool}</div>

            {pendingConfirmation.args && Object.keys(pendingConfirmation.args).length > 0 && (
              <>
                <div className="modal-args-label">Arguments that will be sent</div>
                <pre className="tool-json" style={{ marginBottom: 16 }}>
                  {JSON.stringify(pendingConfirmation.args, null, 2)}
                </pre>
              </>
            )}

            <p className="modal-warning-text">
              This operation <strong>cannot be automatically undone</strong>. Review the arguments carefully
              before proceeding. If you are unsure, click <strong>Cancel</strong>.
            </p>

            <div className="modal-actions">
              <button
                id="confirm-cancel-btn"
                className="btn btn-ghost"
                onClick={() => handleCancel(pendingConfirmation.confirmToken)}
              >
                Cancel
              </button>
              <button
                id="confirm-execute-btn"
                className="btn btn-danger"
                onClick={() => handleConfirm(pendingConfirmation.confirmToken)}
              >
                🚀 Execute Action
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
