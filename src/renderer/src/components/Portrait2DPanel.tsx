import { useMemo, useState } from 'react'
import { useProjectStore } from '../store/projectStore'
import { useUIStore } from '../store/uiStore'
import { buildPortrait2D } from '../core/spec/portrait2dLogic'
import { toDataUrl } from '../core/providers/modelExporter'

/**
 * Phase 3-4: 2D layered portrait preview + export.
 * Pure frontend SVG generation - no backend, no network, no third-party deps.
 * Honest status: "2D layered / Live2D-ready", NOT an official Cubism runtime.
 */
export default function Portrait2DPanel(): JSX.Element {
  const open = useUIStore((s) => s.portrait2dOpen)
  const close = useUIStore((s) => s.closePortrait2D)
  const spec = useProjectStore((s) => s.project.spec)
  const characterAsset = useProjectStore((s) => s.project.characterAsset)
  const [busy, setBusy] = useState(false)

  const output = useMemo(() => buildPortrait2D(spec, characterAsset), [spec, characterAsset])

  if (!open) return <></>

  const overlayStyle: React.CSSProperties = {
    position: 'fixed',
    inset: 0,
    zIndex: 100,
    background: 'rgba(0,0,0,0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center'
  }
  const boxStyle: React.CSSProperties = {
    width: 560,
    maxWidth: '92vw',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    borderRadius: 12,
    padding: 18,
    boxShadow: '0 12px 40px rgba(0,0,0,0.5)',
    display: 'flex',
    gap: 16
  }
  const previewStyle: React.CSSProperties = {
    width: 240,
    height: 320,
    flex: '0 0 240px',
    background: 'var(--bg)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center'
  }

  const handleExport = async (): Promise<void> => {
    if (output.status !== 'ok') return
    setBusy(true)
    try {
      const dataUrl = toDataUrl(new TextEncoder().encode(output.result.svg).buffer, 'image/svg+xml')
      const result = await window.aivcs.exportModel(dataUrl, output.result.fileName)
      if (result.ok) window.alert(`已导出到：\n${result.path}`)
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const statusLine =
    output.status === 'ok'
      ? '2D Layered / Live2D-ready（非 Cubism Runtime）'
      : `2D 暂不支持：${output.bodyType}`

  return (
    <div style={overlayStyle} onClick={close}>
      <div style={boxStyle} onClick={(e) => e.stopPropagation()}>
        <div style={previewStyle}>
          {output.status === 'ok' ? (
            <img
              src={toDataUrl(new TextEncoder().encode(output.result.svg).buffer, 'image/svg+xml')}
              alt="2D 立绘预览"
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          ) : (
            <span style={{ fontSize: 12, color: 'var(--text-dim)', padding: 12, textAlign: 'center' }}>
              {output.reason}
            </span>
          )}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>2D 立绘</div>
          <div
            style={{
              fontSize: 11,
              color: 'var(--accent)',
              marginBottom: 8,
              lineHeight: 1.5
            }}
          >
            {statusLine}
            {output.status === 'ok' && (
              <div style={{ color: 'var(--text-faint)', marginTop: 2 }}>
                {output.result.descriptor.layers.length} 个图层 · front 视图 · 非官方 Cubism 模型
              </div>
            )}
          </div>

          {output.status === 'ok' && (
            <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.6, marginBottom: 12 }}>
              <div>图层（按绘制顺序）：{output.result.descriptor.layers.map((l) => l.id).join(' → ')}</div>
              {output.result.descriptor.backPattern && <div>背纹（metadata）：{output.result.descriptor.backPattern}</div>}
              <div>physics / parameter / deformer / motion：无</div>
              <div>cubism.present：false</div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            {output.status === 'ok' && (
              <button className="btn btn--primary" disabled={busy} onClick={() => void handleExport()}>
                {busy ? '导出中…' : '导出 .svg'}
              </button>
            )}
            <button className="btn btn--ghost" onClick={close}>
              关闭
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
