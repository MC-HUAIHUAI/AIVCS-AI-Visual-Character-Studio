import { useState } from 'react'
import { useProjectStore } from '../store/projectStore'
import { useUIStore } from '../store/uiStore'
import { getViewportManager } from '../three/controller'
import { modelExporters, toDataUrl } from '../core/providers/modelExporter'
import { fetchVrmBytes } from '../core/providers/httpProvider'
import {
  canExportVrm,
  vrmErrorText,
  vrmExportDefaultName
} from '../core/spec/vrmExportLogic'

export default function TitleBar(): JSX.Element {
  const isDirty = useProjectStore((s) => s.isDirty)
  const save = useProjectStore((s) => s.save)
  const load = useProjectStore((s) => s.load)
  const newProject = useProjectStore((s) => s.newProject)
  const projectName = useProjectStore((s) => s.project.name)
  const specName = useProjectStore((s) => s.project.spec.name)
  const specBodyType = useProjectStore((s) => s.project.spec.bodyType)
  const models = useProjectStore((s) => s.project.models)
  const selectedModelId = useProjectStore((s) => s.selectedModelId)
  const backendOnline = useUIStore((s) => s.backendOnline)
  const openSettings = useUIStore((s) => s.openSettings)
  const openPortrait2D = useUIStore((s) => s.openPortrait2D)
  const [busy, setBusy] = useState(false)

  const selectedModel = models.find((m) => m.id === selectedModelId) ?? null
  const vrmAvailable = canExportVrm(selectedModel, backendOnline)

  const handleNew = (): void => {
    if (isDirty && !window.confirm('当前项目有未保存的更改，仍要新建项目吗？')) return
    newProject(`项目 ${new Date().toLocaleTimeString()}`)
  }

  const handleOpen = async (): Promise<void> => {
    if (isDirty && !window.confirm('当前项目有未保存的更改，仍要打开其他项目吗？')) return
    await load()
  }

  const handleSave = (): void => {
    void save()
  }

  const handleExport = async (): Promise<void> => {
    const manager = getViewportManager()
    const root = manager?.getModelRoot()
    if (!root) {
      window.alert('视口中没有可导出的模型。')
      return
    }
    setBusy(true)
    try {
      const exporter = modelExporters.glb
      const out = await exporter.exportModel(root, { binary: true, name: specName || 'character' })
      const result = await window.aivcs.exportModel(out.dataUrl, out.fileName)
      if (result.ok) window.alert(`已导出到：\n${result.path}`)
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleExportVrm = async (): Promise<void> => {
    if (!selectedModel) return
    setBusy(true)
    try {
      // body_type is passed through VERBATIM from spec.bodyType - never guessed
      // or converted; the backend whitelist is the source of truth.
      const { bytes, mime } = await fetchVrmBytes(selectedModel.id, specBodyType, specName)
      const dataUrl = toDataUrl(bytes, mime)
      const result = await window.aivcs.exportModel(dataUrl, vrmExportDefaultName(specName))
      if (result.ok) window.alert(`已导出到：\n${result.path}`)
    } catch (err) {
      const e = err as { status?: number | null; detail?: string | null; isNetwork?: boolean }
      window.alert(vrmErrorText(e.status ?? null, e.detail ?? null, e.isNetwork === true))
    } finally {
      setBusy(false)
    }
  }

  return (
    <header className="titlebar">
      <div className="titlebar__brand">
        <span className="titlebar__logo">AV</span>
        <span>AIVCS</span>
        <span style={{ color: 'var(--text-faint)', fontWeight: 400 }}>{projectName}</span>
        {isDirty && <span style={{ color: 'var(--warning)', fontSize: 11 }}>●</span>}
      </div>

      <div className="titlebar__sep" />

      <div className="titlebar__actions">
        <button className="btn btn--ghost btn--sm" onClick={handleNew}>
          新建
        </button>
        <button className="btn btn--ghost btn--sm" onClick={() => void handleOpen()}>
          打开
        </button>
        <button className="btn btn--ghost btn--sm" onClick={handleSave}>
          保存{isDirty ? ' *' : ''}
        </button>
        <button className="btn btn--ghost btn--sm" onClick={() => void handleExport()} disabled={busy}>
          {busy ? '导出中…' : '导出 GLB'}
        </button>
        <button
          className="btn btn--ghost btn--sm"
          onClick={() => void handleExportVrm()}
          disabled={busy || !vrmAvailable}
          title={
            vrmAvailable
              ? '导出 VRM（本地后端 /api/v1/models/{id}/vrm）'
              : backendOnline
                ? '当前选中的模型不是后端生成的模型，无法导出 VRM'
                : '后端离线，无法导出 VRM'
          }
        >
          {busy ? '导出中…' : '导出 VRM'}
        </button>
        <button
          className="btn btn--ghost btn--sm"
          onClick={openPortrait2D}
          title="2D 分层立绘预览与导出（前端 SVG，非 Cubism Runtime）"
        >
          2D 立绘
        </button>
        <button className="btn btn--ghost btn--sm" onClick={openSettings}>
          设置
        </button>
      </div>

      <div style={{ flex: 1 }} />

      <div className="titlebar__actions" title={backendOnline ? 'FastAPI 后端在线' : 'FastAPI 后端离线（运行 npm run backend 启动）'}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 11.5,
            color: 'var(--text-dim)'
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: backendOnline ? 'var(--success)' : 'var(--danger)'
            }}
          />
          {backendOnline ? '后端在线' : '后端离线'}
        </span>
      </div>
    </header>
  )
}
