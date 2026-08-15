import { useMemo, useState } from 'react'
import { useProjectStore } from '../store/projectStore'
import { useUIStore } from '../store/uiStore'
import {
  buildModelInfoRows,
  canConvertToVrm,
  textureStatusLabel
} from '../core/spec/modelInfoLogic'
import { modelAssetFromResult } from '../core/spec/generationLogic'
import { convertModelToVrm } from '../core/providers/httpProvider'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function sourceBadge(source: 'demo' | 'generated' | 'imported'): JSX.Element {
  switch (source) {
    case 'demo':
      return <span className="badge badge--demo">演示</span>
    case 'generated':
      return <span className="badge badge--gen">AI</span>
    default:
      return <span className="badge">导入</span>
  }
}

export default function AssetsPanel(): JSX.Element {
  const project = useProjectStore((s) => s.project)
  const selectedModelId = useProjectStore((s) => s.selectedModelId)
  const selectedImageId = useProjectStore((s) => s.selectedImageId)
  const selectModel = useProjectStore((s) => s.selectModel)
  const selectImage = useProjectStore((s) => s.selectImage)
  const importImages = useProjectStore((s) => s.importImages)
  const removeImage = useProjectStore((s) => s.removeImage)
  const removeModel = useProjectStore((s) => s.removeModel)
  const addModel = useProjectStore((s) => s.addModel)
  const clearReferences = useUIStore((s) => s.clearReferences)

  const [converting, setConverting] = useState(false)
  const [vrmError, setVrmError] = useState<string | null>(null)

  const selectedModel = project.models.find((m) => m.id === selectedModelId) ?? null
  const hasDerivedVrm = selectedModel
    ? project.models.some((m) => m.sourceModelId === selectedModel.id)
    : false
  const modelInfo = useMemo(
    () =>
      selectedModel
        ? buildModelInfoRows(selectedModel, {
            hasDerivedVrm,
            bodyType: project.spec.bodyType
          })
        : null,
    [selectedModel, hasDerivedVrm, project.spec.bodyType]
  )

  const canVrm = selectedModel ? canConvertToVrm(project.spec.bodyType) : false
  const selectedTexture = selectedModel ? textureStatusLabel(selectedModel) : null

  const handleConvertToVrm = async (): Promise<void> => {
    if (!selectedModel) return
    setConverting(true)
    setVrmError(null)
    try {
      const res = await convertModelToVrm(selectedModel.id, {
        bodyType: project.spec.bodyType,
        characterType: project.spec.characterType,
        modelName: project.spec.name || 'AIVCS Character'
      })
      if (!res.ok || !res.bytes || !res.vrmModelId) {
        setVrmError(res.error ?? 'VRM 转换失败')
        return
      }
      const vrmModel = modelAssetFromResult(res.vrmModelId, `${selectedModel.name} (VRM)`, {
        format: 'vrm',
        mime: 'model/gltf-binary',
        providerId: 'local3d-rig',
        sourceJobId: selectedModel.sourceJobId,
        sourceModelId: selectedModel.id,
        sizeBytes: res.bytes.byteLength,
        glbStats: res.stats
      })
      addModel(vrmModel, res.bytes) // adds as a NEW model; original GLB preserved
    } catch (err) {
      setVrmError(err instanceof Error ? err.message : String(err))
    } finally {
      setConverting(false)
    }
  }

  return (
    <aside className="panel panel--left">
      <div className="panel__header">
        <span className="panel__title">
          <span className="panel__dot" />
          素材库
        </span>
      </div>

      <div className="panel__body">
        <div className="asset-group">
          <div className="asset-group__label">
            模型 <span className="asset-group__count">({project.models.length})</span>
          </div>
          {project.models.map((model) => (
            <div
              key={model.id}
              className={`asset-item${selectedModelId === model.id ? ' asset-item--selected' : ''}`}
              onClick={() => selectModel(model.id)}
            >
              <div className="asset-item__thumb asset-item__thumb--model">
                {model.format === 'vrm' ? 'VRM' : '3D'}
              </div>
              <div className="asset-item__info">
                <div className="asset-item__name">{model.name}</div>
                <div className="asset-item__meta">
                  {model.format.toUpperCase()}
                  {model.texture?.supported ? ' · 有纹理' : ' · shape-only'}
                  {model.format === 'vrm' ? ' · VRM' : ''}
                </div>
              </div>
              {sourceBadge(model.source)}
              {project.models.length > 1 && model.source !== 'demo' && (
                <button
                  className="ref-thumb__remove"
                  style={{ position: 'static', opacity: 1 }}
                  title="移除模型"
                  onClick={(e) => {
                    e.stopPropagation()
                    removeModel(model.id)
                  }}
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>

        <div className="asset-group">
          <div className="asset-group__label">
            参考图 <span className="asset-group__count">({project.images.length})</span>
          </div>
          {project.images.length === 0 ? (
            <div className="empty-hint">
              还没有参考图。
              <br />
              导入 PNG / JPG / WEBP
            </div>
          ) : (
            <div className="ref-grid">
              {project.images.map((img) => (
                <div
                  key={img.id}
                  className={`ref-thumb${selectedImageId === img.id ? ' ref-thumb--selected' : ''}`}
                  title={`${img.name}\n${img.width}×${img.height} · ${formatBytes(img.bytes)}`}
                  onClick={() => selectImage(selectedImageId === img.id ? null : img.id)}
                >
                  <img src={img.dataUrl} alt={img.name} />
                  <button
                    className="ref-thumb__remove"
                    onClick={(e) => {
                      e.stopPropagation()
                      removeImage(img.id)
                      clearReferences()
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {modelInfo && (
          <div className="asset-group">
            <div className="asset-group__label">模型信息</div>
            <div
              style={{
                fontSize: 11.5,
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '8px 10px'
              }}
            >
              {modelInfo.rows.map((r) => (
                <div
                  key={r.label}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 8,
                    padding: '2px 0'
                  }}
                >
                  <span style={{ color: 'var(--text-dim)' }}>{r.label}</span>
                  <span style={{ textAlign: 'right' }}>{r.value ?? '—'}</span>
                </div>
              ))}
              {modelInfo.warnings.length > 0 && (
                <div style={{ fontSize: 11, color: 'var(--warning)', marginTop: 6, lineHeight: 1.5 }}>
                  {modelInfo.warnings.map((w, i) => (
                    <div key={i}>⚠ {w}</div>
                  ))}
                </div>
              )}
              {modelInfo.normalizations.length > 0 && (
                <div style={{ fontSize: 11, color: 'var(--accent)', marginTop: 6, lineHeight: 1.5 }}>
                  {modelInfo.normalizations.map((n, i) => (
                    <div key={i}>ℹ {n}</div>
                  ))}
                </div>
              )}
            </div>

            {selectedModel?.format !== 'vrm' && (
              <div style={{ marginTop: 8 }}>
                {canVrm ? (
                  <button
                    className="btn btn--sm btn--primary"
                    disabled={converting}
                    onClick={() => void handleConvertToVrm()}
                  >
                    {converting ? 'VRM 分析中…' : '转换为 VRM'}
                  </button>
                ) : (
                  <div style={{ fontSize: 11, color: 'var(--warning)', lineHeight: 1.5 }}>
                    不支持 VRM 骨骼绑定（当前角色为非人体 / 非 humanoid 体型）。
                  </div>
                )}
                {vrmError && (
                  <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 6, lineHeight: 1.5 }}>
                    转换失败：{vrmError}
                  </div>
                )}
                <div style={{ fontSize: 10.5, color: 'var(--text-faint)', marginTop: 4, lineHeight: 1.5 }}>
                  转换生成独立的 VRM 模型，原始 GLB 保持不变。
                  {selectedTexture ? ` · ${selectedTexture}` : ''}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="panel__footer">
        <button className="btn btn--block" onClick={() => void importImages()}>
          导入图片
        </button>
      </div>
    </aside>
  )
}
