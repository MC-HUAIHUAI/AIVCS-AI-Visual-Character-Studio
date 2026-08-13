import { useMemo, useState } from 'react'
import { useProjectStore } from '../store/projectStore'
import { useUIStore } from '../store/uiStore'
import { useVisionStore } from '../store/visionStore'
import { visionProviders } from '../core/providers/visionRegistry'
import type { VisionImageInput } from '../core/providers/visionProvider'
import SpecReviewList from './SpecReviewList'

const LOW_CONFIDENCE_THRESHOLD = 0.5

export default function VisionAnalysisPanel(): JSX.Element {
  const images = useProjectStore((s) => s.project.images)
  const updateSpec = useProjectStore((s) => s.updateSpec)
  const selectedReferenceIds = useUIStore((s) => s.selectedReferenceIds)

  const visionStatus = useVisionStore((s) => s.status)
  const progress = useVisionStore((s) => s.progress)
  const error = useVisionStore((s) => s.error)
  const result = useVisionStore((s) => s.result)
  const analyze = useVisionStore((s) => s.analyze)
  const reset = useVisionStore((s) => s.reset)

  const [providerId, setProviderId] = useState(visionProviders[0].id)

  const selectedImages = useMemo(
    () => images.filter((i) => selectedReferenceIds.includes(i.id)),
    [images, selectedReferenceIds]
  )
  const primaryImage = selectedImages[0] ?? null
  const analyzing = visionStatus === 'analyzing'
  const provider = visionProviders.find((p) => p.id === providerId) ?? visionProviders[0]

  const handleAnalyze = async (): Promise<void> => {
    if (!primaryImage) return
    // Phase 1 leftover fix: keep spec.referenceImageIds in sync with the UI
    // selection before analysis, so the same ids flow into the vision request.
    updateSpec({ referenceImageIds: [...selectedReferenceIds] })

    const refs: VisionImageInput[] = selectedImages.map((img) => ({
      imageId: img.id,
      dataUrl: img.dataUrl,
      view: img.view ?? null
    }))
    await analyze(refs, providerId)
  }

  const lowConfidence = result !== null && result.confidence < LOW_CONFIDENCE_THRESHOLD

  return (
    <div className="spec-field">
      <label>AI 视觉分析</label>

      {primaryImage ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <img
            src={primaryImage.dataUrl}
            alt={primaryImage.name}
            style={{ width: 48, height: 48, borderRadius: 6, objectFit: 'cover', border: '1px solid var(--border)' }}
          />
          <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.5 }}>
            {primaryImage.name}
            <br />
            当前参考图 · 已选 {selectedImages.length} 张
          </div>
        </div>
      ) : (
        <div className="empty-hint" style={{ padding: '8px 0' }}>
          请先在上方选择一张参考图。
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
          disabled={!primaryImage || analyzing}
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

      {result && result.warnings.length > 0 && (
        <div style={{ fontSize: 11.5, color: 'var(--warning)', margin: '4px 0', lineHeight: 1.5 }}>
          {result.warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}

      {visionStatus === 'success' && <SpecReviewList />}
    </div>
  )
}
