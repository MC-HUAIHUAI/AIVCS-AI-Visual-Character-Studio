import { useMemo, useState } from 'react'
import type { ReferenceView } from '@shared/types'
import { useProjectStore } from '../store/projectStore'
import { useUIStore } from '../store/uiStore'
import { useVisionStore } from '../store/visionStore'
import { visionProviders } from '../core/providers/visionRegistry'
import type { VisionImageInput } from '../core/providers/visionProvider'
import { missingViewWarning, PER_VIEW_MISSING_MESSAGE } from '../core/spec/visionReviewLogic'
import SpecReviewList from './SpecReviewList'
import ConflictResolveList from './ConflictResolveList'

const LOW_CONFIDENCE_THRESHOLD = 0.5
const MAX_REFERENCES = 4

const VIEW_OPTIONS: { value: ReferenceView; label: string }[] = [
  { value: 'front', label: '正面' },
  { value: 'side', label: '侧面' },
  { value: 'back', label: '背面' },
  { value: 'custom', label: '自定义' }
]

const VIEW_LABEL: Record<string, string> = {
  front: '正面',
  side: '侧面',
  back: '背面',
  custom: '自定义'
}

export default function VisionAnalysisPanel(): JSX.Element {
  const images = useProjectStore((s) => s.project.images)
  const updateSpec = useProjectStore((s) => s.updateSpec)
  const updateImage = useProjectStore((s) => s.updateImage)
  const selectedReferenceIds = useUIStore((s) => s.selectedReferenceIds)

  const visionStatus = useVisionStore((s) => s.status)
  const progress = useVisionStore((s) => s.progress)
  const error = useVisionStore((s) => s.error)
  const result = useVisionStore((s) => s.result)
  const viewAnalyses = useVisionStore((s) => s.viewAnalyses)
  const conflicts = useVisionStore((s) => s.conflicts)
  const resolved = useVisionStore((s) => s.resolved)
  const skipped = useVisionStore((s) => s.skipped)
  const analyze = useVisionStore((s) => s.analyze)
  const reset = useVisionStore((s) => s.reset)

  const [providerId, setProviderId] = useState(visionProviders[0].id)

  const selectedImages = useMemo(
    () => images.filter((i) => selectedReferenceIds.includes(i.id)),
    [images, selectedReferenceIds]
  )
  const analyzing = visionStatus === 'analyzing'
  const provider = visionProviders.find((p) => p.id === providerId) ?? visionProviders[0]
  const overLimit = selectedImages.length > MAX_REFERENCES
  const canAnalyze = selectedImages.length > 0 && !overLimit && !analyzing

  const refsViews = useMemo(() => selectedImages.map((i) => i.view ?? 'front'), [selectedImages])
  const viewWarning = visionStatus === 'success' ? missingViewWarning(refsViews) : null
  const unresolvedCount = conflicts.filter((c) => resolved[c.field] === undefined && !skipped[c.field]).length

  const handleAnalyze = async (): Promise<void> => {
    if (selectedImages.length === 0) return
    // Phase 1 leftover fix: keep spec.referenceImageIds in sync with the UI
    // selection before analysis, so the same ids flow into the vision request.
    updateSpec({ referenceImageIds: [...selectedReferenceIds] })

    const refs: VisionImageInput[] = selectedImages.map((img) => ({
      imageId: img.id,
      dataUrl: img.dataUrl,
      view: img.view ?? 'front'
    }))
    await analyze(refs, providerId)
  }

  const lowConfidence = result !== null && result.confidence < LOW_CONFIDENCE_THRESHOLD

  return (
    <div className="spec-field">
      <label>AI 视觉分析</label>

      {selectedImages.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
          {selectedImages.map((img) => (
            <div
              key={img.id}
              style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}
            >
              <img
                src={img.dataUrl}
                alt={img.name}
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 6,
                  objectFit: 'cover',
                  border: '1px solid var(--border)'
                }}
              />
              <span
                style={{ color: 'var(--text-dim)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                title={img.name}
              >
                {img.name}
              </span>
              <select
                value={img.view ?? 'front'}
                onChange={(e) => updateImage(img.id, { view: e.target.value as ReferenceView })}
                style={{ width: 88, padding: '3px 6px', fontSize: 11.5 }}
              >
                {VIEW_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          ))}
          <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>
            已选 {selectedImages.length} 张（最多 {MAX_REFERENCES} 张）
            {selectedImages.length === 1 ? ' · 单图模式' : ' · 多视角 joint 模式'}
          </div>
        </div>
      ) : (
        <div className="empty-hint" style={{ padding: '8px 0' }}>
          请先在上方选择参考图。
        </div>
      )}

      {overLimit && (
        <div style={{ color: 'var(--danger)', fontSize: 12, margin: '4px 0' }}>
          最多只能选择 {MAX_REFERENCES} 张参考图。
        </div>
      )}

      <div className="chip-row" style={{ marginBottom: 8 }}>
        {visionProviders.map((p) => (
          <button
            key={p.id}
            className={`chip${providerId === p.id ? ' chip--active' : ''}`}
            title={p.description}
            onClick={() => setProviderId(p.id)}
          >
            {p.displayName}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8 }}>
        <button
          className="btn btn--primary"
          disabled={!canAnalyze}
          onClick={() => void handleAnalyze()}
        >
          {analyzing ? '分析中…' : '开始分析'}
        </button>
        {visionStatus === 'success' && (
          <button className="btn" onClick={reset}>
            重新分析
          </button>
        )}
      </div>

      {analyzing && (
        <div style={{ marginBottom: 8 }}>
          <div className="progress-bar">
            <div className="progress-bar__fill" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
        </div>
      )}

      <div className="provider-row">
        <span className={`provider-dot ${provider.requiresBackend ? 'provider-dot--off' : 'provider-dot--ok'}`} />
        状态：{analyzing ? '分析中' : visionStatus === 'success' ? '分析完成' : visionStatus === 'error' ? '分析失败' : 'Mock 模式'}
      </div>

      {error && (
        <div style={{ color: 'var(--danger)', fontSize: 12, margin: '6px 0' }}>{error}</div>
      )}

      {lowConfidence && (
        <div
          style={{
            fontSize: 11.5,
            color: 'var(--warning)',
            background: 'rgba(242,177,52,0.1)',
            border: '1px solid rgba(242,177,52,0.35)',
            borderRadius: 6,
            padding: '6px 8px',
            margin: '6px 0',
            lineHeight: 1.5
          }}
        >
          分析置信度较低，请仔细确认以下 AI 建议。
        </div>
      )}

      {viewWarning && (
        <div style={{ fontSize: 11.5, color: 'var(--warning)', margin: '4px 0', lineHeight: 1.5 }}>
          ⚠ {viewWarning}
        </div>
      )}

      {result && result.warnings.length > 0 && (
        <div style={{ fontSize: 11.5, color: 'var(--warning)', margin: '4px 0', lineHeight: 1.5 }}>
          {result.warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}

      {visionStatus === 'success' && (
        <>
          {unresolvedCount > 0 && <ConflictResolveList />}
          <SpecReviewList />

          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 4 }}>
              每视角分析摘要
            </div>
            {viewAnalyses.length === 0 ? (
              <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{PER_VIEW_MISSING_MESSAGE}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {viewAnalyses.map((pv, i) => (
                  <div
                    key={`${pv.view}_${pv.sourceImageId}_${i}`}
                    style={{
                      fontSize: 11.5,
                      padding: '4px 6px',
                      borderRadius: 6,
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border)',
                      lineHeight: 1.5
                    }}
                  >
                    <span style={{ color: 'var(--accent)' }}>
                      {VIEW_LABEL[pv.view] ?? pv.view}
                    </span>{' '}
                    · {pv.sourceImageId} · 置信度 {Math.round(pv.confidence * 100)}%
                    {pv.notes.length > 0 && (
                      <div style={{ color: 'var(--text-dim)' }}>备注：{pv.notes.join('；')}</div>
                    )}
                    {pv.warnings.length > 0 && (
                      <div style={{ color: 'var(--warning)' }}>警告：{pv.warnings.join('；')}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
