import React, { useState } from 'react'

/**
 * ConfirmActionModal — shown when the agent wants to execute a write action.
 *
 * Props:
 *   action          { tool: string, args: object, confirmToken: string }
 *   onConfirm(token) — user clicked Execute
 *   onCancel(token)  — user clicked Cancel
 */
export default function ConfirmActionModal({ action, onConfirm, onCancel }) {
  const [confirming, setConfirming] = useState(false)

  if (!action) return null
  const { tool, args, confirmToken } = action

  const handleConfirm = async () => {
    setConfirming(true)
    await onConfirm(confirmToken)
  }

  const handleCancel = () => {
    onCancel(confirmToken)
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="modal-card">
        {/* Header */}
        <div className="modal-header">
          <div className="modal-danger-icon" aria-hidden="true">⚠️</div>
          <div>
            <div id="confirm-title" className="modal-title">Confirm Write Action</div>
            <div className="modal-subtitle">This action will make changes to your AWS environment</div>
          </div>
        </div>

        {/* Tool name */}
        <div className="modal-tool-name" aria-label={`Tool: ${tool}`}>{tool}</div>

        {/* Arguments */}
        {args && Object.keys(args).length > 0 && (
          <>
            <div className="modal-args-label">Arguments that will be sent</div>
            <pre className="tool-json" style={{ marginBottom: 16 }}>
              {JSON.stringify(args, null, 2)}
            </pre>
          </>
        )}

        {/* Warning */}
        <p className="modal-warning-text">
          This operation <strong>cannot be automatically undone</strong>. Review the arguments carefully
          before proceeding. If you are unsure, click <strong>Cancel</strong> and ask your AWS administrator.
        </p>

        {/* Actions */}
        <div className="modal-actions">
          <button
            id="confirm-cancel-btn"
            className="btn btn-ghost"
            onClick={handleCancel}
            disabled={confirming}
          >
            Cancel
          </button>
          <button
            id="confirm-execute-btn"
            className="btn btn-danger"
            onClick={handleConfirm}
            disabled={confirming}
            aria-busy={confirming}
          >
            {confirming ? '⏳ Executing…' : '🚀 Execute Action'}
          </button>
        </div>
      </div>
    </div>
  )
}
