import React, { useState } from 'react'

/**
 * AWS service icon mapping — returns an emoji for known service prefixes.
 */
function getServiceIcon(toolName) {
  const t = toolName.toLowerCase()
  if (t.includes('lambda')) return '⚡'
  if (t.includes('s3')) return '🪣'
  if (t.includes('ec2')) return '🖥'
  if (t.includes('rds') || t.includes('database')) return '🗄'
  if (t.includes('cloudwatch') || t.includes('metric') || t.includes('log')) return '📊'
  if (t.includes('iam')) return '🔐'
  if (t.includes('cost') || t.includes('billing')) return '💰'
  if (t.includes('ecs') || t.includes('fargate') || t.includes('container')) return '📦'
  if (t.includes('eks') || t.includes('kubernetes')) return '🎡'
  if (t.includes('sns') || t.includes('sqs') || t.includes('event')) return '📨'
  if (t.includes('dynamo')) return '⚡'
  if (t.includes('cloudformation') || t.includes('cfn')) return '🏗'
  if (t.includes('ssm') || t.includes('parameter')) return '🔧'
  if (t.includes('secret')) return '🔑'
  if (t.includes('route') || t.includes('dns')) return '🌐'
  if (t.includes('elb') || t.includes('alb') || t.includes('load')) return '⚖️'
  if (t.includes('docs') || t.includes('documentation')) return '📚'
  return '🔧'
}

/**
 * ToolCallCard — collapsible card shown inline in the chat for each MCP tool call.
 *
 * Props:
 *   tool    { name, args, result, status: 'running'|'done'|'error' }
 */
export default function ToolCallCard({ tool }) {
  const [open, setOpen] = useState(false)
  const { name, args, result, status = 'running' } = tool

  const statusLabel = status === 'running' ? 'Running…'
    : status === 'done' ? 'Done'
    : 'Error'

  return (
    <div className="tool-card" aria-label={`Tool call: ${name}`}>
      <div
        className="tool-card-header"
        onClick={() => setOpen(o => !o)}
        role="button"
        aria-expanded={open}
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && setOpen(o => !o)}
      >
        <div className="tool-icon" aria-hidden="true">{getServiceIcon(name)}</div>
        <span className="tool-name">{name}</span>
        <span className={`tool-status ${status}`}>{statusLabel}</span>
        <span className={`tool-chevron${open ? ' open' : ''}`} aria-hidden="true">▾</span>
      </div>

      {open && (
        <div className="tool-card-body">
          {args && Object.keys(args).length > 0 && (
            <>
              <div className="tool-section-label">Arguments</div>
              <pre className="tool-json">{JSON.stringify(args, null, 2)}</pre>
            </>
          )}
          {result && (
            <>
              <div className="tool-section-label" style={{ marginTop: 10 }}>Result</div>
              <pre className="tool-json">{typeof result === 'string' ? result : JSON.stringify(result, null, 2)}</pre>
            </>
          )}
          {!result && status === 'running' && (
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic', marginTop: '10px' }}>
              Waiting for response…
            </div>
          )}
        </div>
      )}
    </div>
  )
}
