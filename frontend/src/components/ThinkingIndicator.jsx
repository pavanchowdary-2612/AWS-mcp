import React from 'react'

const AssistantIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 17L12 22L22 17" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 12L12 17L22 12" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

/**
 * Thinking indicator — animated dots shown while the agent is processing.
 */
export default function ThinkingIndicator({ label = 'Thinking…' }) {
  return (
    <div className="thinking-row">
      <div className="message-avatar assistant" aria-hidden="true"><AssistantIcon /></div>
      <div className="thinking-bubble" role="status" aria-label={label}>
        <div className="thinking-dots" aria-hidden="true">
          <span className="thinking-dot" />
          <span className="thinking-dot" />
          <span className="thinking-dot" />
        </div>
        <span className="thinking-label">{label}</span>
      </div>
    </div>
  )
}
