import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ToolCallCard from './ToolCallCard'

const AssistantIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 17L12 22L22 17" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 12L12 17L22 12" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

const UserIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M12 11C14.2091 11 16 9.20914 16 7C16 4.79086 14.2091 3 12 3C9.79086 3 8 4.79086 8 7C8 9.20914 9.79086 11 12 11Z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

/**
 * MessageBubble — renders a single conversation message.
 *
 * Props:
 *   message { id, role, content, tools?, timestamp, code? }
 */
export default function MessageBubble({ message }) {
  const { role, content, tools, timestamp } = message

  const timeStr = timestamp
    ? new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : ''

  if (role === 'error') {
    return (
      <div className="message-row" style={{ flexDirection: 'row' }}>
        <div className="message-avatar assistant" aria-hidden="true"><AssistantIcon /></div>
        <div className="message-content-wrap">
          <div className="error-bubble" role="alert" style={{ background: 'var(--danger-dim)', color: 'var(--danger)', padding: '12px 16px', borderRadius: 'var(--radius-md)', border: '1px solid rgba(239,68,68,0.3)', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14.5px' }}>
            <span aria-hidden="true">⚠️</span>
            <span>{content}</span>
          </div>
          {timeStr && <span className="message-timestamp">{timeStr}</span>}
        </div>
      </div>
    )
  }

  if (role === 'user') {
    return (
      <div className="message-row user">
        <div className="message-avatar user" aria-hidden="true"><UserIcon /></div>
        <div className="message-content-wrap">
          <div className="message-bubble user">{content}</div>
          {timeStr && <span className="message-timestamp">{timeStr}</span>}
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="message-row">
      <div className="message-avatar assistant" aria-hidden="true"><AssistantIcon /></div>
      <div className="message-content-wrap" style={{ maxWidth: '100%', flex: 1 }}>
        {/* Tool call cards (above the text response) */}
        {tools && tools.length > 0 && (
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '8px' }}>
            {tools.map((tool) => (
              <ToolCallCard key={tool.name} tool={tool} />
            ))}
          </div>
        )}

        {/* Text content */}
        {content && (
          <div className="message-bubble assistant">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Open links in a new tab safely
                a: ({ node, ...props }) => (
                  <a {...props} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-bright)', textDecoration: 'none' }} />
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        )}

        {timeStr && <span className="message-timestamp">{timeStr}</span>}
      </div>
    </div>
  )
}
