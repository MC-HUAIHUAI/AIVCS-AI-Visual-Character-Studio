import { useState } from 'react'
import { useProjectStore } from '../store/projectStore'
import { useUIStore } from '../store/uiStore'
import { getViewportManager } from '../three/controller'
import { modelExporters } from '../core/providers/modelExporter'

export default function TitleBar(): JSX.Element {
  const isDirty = useProjectStore((s) => s.isDirty)
  const save = useProjectStore((s) => s.save)
  const load = useProjectStore((s) => s.load)
  const newProject = useProjectStore((s) => s.newProject)
  const projectName = useProjectStore((s) => s.project.name)
  const specName = useProjectStore((s) => s.project.spec.name)
  const backendOnline = useUIStore((s) => s.backendOnline)
  const [busy, setBusy] = useState(false)

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
