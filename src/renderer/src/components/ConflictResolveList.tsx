import { useVisionStore } from '../store/visionStore'
import { enumLabel } from '../core/spec/visionReviewLogic'

const VIEW_LABEL: Record<string, string> = {
  front: '正面',
  side: '侧面',
  back: '背面',
  custom: '自定义'
}

function candidateValueLabel(field: string, value: unknown): string {
  const top = field.split('.')[0]
  const leaf = field.split('.').slice(1)
  if (leaf.length === 1 && top === 'species' && leaf[0] === 'primary') return enumLabel('species', value)
  if (top === 'anatomy' && typeof value === 'boolean') return value ? '有' : '无'
  return enumLabel(field, value)
}

export default function ConflictResolveList(): JSX.Element {
  const conflicts = useVisionStore((s) => s.conflicts)
  const resolved = useVisionStore((s) => s.resolved)
  const skipped = useVisionStore((s) => s.skipped)
  const resolveConflict = useVisionStore((s) => s.resolveConflict)
  const resolveConflictDefault = useVisionStore((s) => s.resolveConflictDefault)
  const skipConflict = useVisionStore((s) => s.skipConflict)

  const unresolved = conflicts.filter((c) => resolved[c.field] === undefined && !skipped[c.field])
  const skippedList = conflicts.filter((c) => skipped[c.field])

  if (unresolved.length === 0 && skippedList.length === 0) return <></>

  return (
    <div
      style={{
        border: '1px solid rgba(242,177,52,0.4)',
        borderRadius: 8,
        overflow: 'hidden',
        marginBottom: 8
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '6px 8px',
          background: 'rgba(242,177,52,0.1)',
          borderBottom: '1px solid rgba(242,177,52,0.3)'
        }}
      >
        <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--warning)' }}>
          存在多视角冲突
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
          {unresolved.length} 项待解决
        </span>
      </div>

      {unresolved.map((conflict) => (
        <div
          key={conflict.field}
          style={{
            padding: '8px',
            borderBottom: '1px solid var(--border)',
            background: 'rgba(242,177,52,0.04)'
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>{conflict.fieldLabel}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 6 }}>
            {conflict.candidates.map((candidate, index) => (
              <div
                key={`${index}_${String(candidate.view)}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 12,
                  padding: '4px 6px',
                  borderRadius: 6,
                  background: 'var(--bg-elevated)'
                }}
              >
                <span style={{ width: 44, color: 'var(--text-dim)' }}>
                  {candidate.view ? VIEW_LABEL[candidate.view] ?? candidate.view : '—'}
                </span>
                <span style={{ flex: 1 }}>{candidateValueLabel(conflict.field, candidate.value)}</span>
                <span style={{ color: 'var(--text-faint)', fontSize: 11 }}>
                  {Math.round(candidate.confidence * 100)}%
                </span>
                <button
                  className="btn btn--sm"
                  onClick={() => resolveConflict(conflict.field, index)}
                >
                  采用
                </button>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {conflict.resolvedTo && (
              <span style={{ fontSize: 11, color: 'var(--text-faint)', marginRight: 'auto' }}>
                默认（{VIEW_LABEL[conflict.resolvedTo.view ?? ''] ?? conflict.resolvedTo.view ?? '—'}，
                {Math.round(conflict.resolvedTo.confidence * 100)}%）
              </span>
            )}
            <button className="btn btn--sm" onClick={() => resolveConflictDefault(conflict.field)}>
              采用默认
            </button>
            <button className="btn btn--sm" onClick={() => skipConflict(conflict.field)}>
              跳过
            </button>
          </div>
        </div>
      ))}

      {skippedList.length > 0 && (
        <div style={{ padding: '6px 8px', fontSize: 11, color: 'var(--text-faint)' }}>
          已跳过：{skippedList.map((c) => c.fieldLabel).join('、')}（不会写入角色设定）
        </div>
      )}
    </div>
  )
}
