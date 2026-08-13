import { useVisionStore } from '../store/visionStore'
import type { SuggestionStatus } from '../store/visionStore'

const STATUS_LABEL: Record<SuggestionStatus, string> = {
  pending: '待确认',
  accepted: '已采纳',
  modified: '已修改',
  rejected: '已丢弃'
}

export default function SpecReviewList(): JSX.Element {
  const suggestions = useVisionStore((s) => s.suggestions)
  const acceptSuggestion = useVisionStore((s) => s.acceptSuggestion)
  const rejectSuggestion = useVisionStore((s) => s.rejectSuggestion)
  const acceptAll = useVisionStore((s) => s.acceptAll)
  const rejectAll = useVisionStore((s) => s.rejectAll)
  const hasPending = suggestions.some((s) => s.status === 'pending')

  if (suggestions.length === 0) {
    return (
      <div className="empty-hint" style={{ fontSize: 11.5 }}>
        分析完成，但没有可确认的建议。
      </div>
    )
  }

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          padding: '6px 8px',
          background: 'var(--bg-elevated)',
          borderBottom: '1px solid var(--border)'
        }}
      >
        <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-dim)' }}>AI 建议</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn btn--sm" disabled={!hasPending} onClick={acceptAll}>
            全部采用
          </button>
          <button className="btn btn--sm" disabled={!hasPending} onClick={rejectAll}>
            全部丢弃
          </button>
        </div>
      </div>

      <div>
        {suggestions.map((s) => (
          <div
            key={s.id}
            style={{
              display: 'grid',
              gridTemplateColumns: '110px 1fr auto auto auto',
              gap: 8,
              alignItems: 'center',
              padding: '6px 8px',
              borderBottom: '1px solid var(--border)'
            }}
          >
            <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>{s.fieldLabel}</span>
            <span style={{ fontSize: 12 }}>{s.valueLabel}</span>
            <span
              style={{
                fontSize: 11,
                color: s.confidence !== null && s.confidence < 0.5 ? 'var(--warning)' : 'var(--text-faint)'
              }}
              title="置信度"
            >
              {s.confidence !== null ? `${Math.round(s.confidence * 100)}%` : '—'}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-faint)', width: 52 }}>{STATUS_LABEL[s.status]}</span>
            {s.status === 'pending' ? (
              <div style={{ display: 'flex', gap: 4 }}>
                <button className="btn btn--sm btn--primary" onClick={() => acceptSuggestion(s.id)}>
                  采用
                </button>
                <button className="btn btn--sm" onClick={() => rejectSuggestion(s.id)}>
                  丢弃
                </button>
              </div>
            ) : (
              <span style={{ width: 60 }} />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
