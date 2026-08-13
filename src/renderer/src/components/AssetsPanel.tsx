import { useProjectStore } from '../store/projectStore'
import { useUIStore } from '../store/uiStore'

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
  const clearReferences = useUIStore((s) => s.clearReferences)

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
              <div className="asset-item__thumb asset-item__thumb--model">3D</div>
              <div className="asset-item__info">
                <div className="asset-item__name">{model.name}</div>
                <div className="asset-item__meta">{model.format.toUpperCase()}</div>
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
      </div>

      <div className="panel__footer">
        <button className="btn btn--block" onClick={() => void importImages()}>
          导入图片
        </button>
      </div>
    </aside>
  )
}
