import { useUIStore } from '../store/uiStore'
import {
  external3DDisabledReason,
  external3DReservedNotice,
  isExternal3DReserved,
  validateExternal3DSettings
} from '../core/settings/external3dSettingsLogic'

/**
 * Phase 2.4-D-pre: reserved external 3D provider entry. Pure display + format
 * check. Never triggers any network request / provider call / address probe.
 */
export default function SettingsDialog(): JSX.Element {
  const open = useUIStore((s) => s.settingsOpen)
  const close = useUIStore((s) => s.closeSettings)
  const external3d = useUIStore((s) => s.external3d)
  const setExternal3D = useUIStore((s) => s.setExternal3D)

  if (!open) return <></>

  const issues = validateExternal3DSettings(external3d)

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
    width: 420,
    maxWidth: '90vw',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    borderRadius: 12,
    padding: 18,
    boxShadow: '0 12px 40px rgba(0,0,0,0.5)'
  }

  return (
    <div style={overlayStyle} onClick={close}>
      <div style={boxStyle} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>设置</div>
        <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 14, lineHeight: 1.6 }}>
          当前版本仅保留配置契约，未接入任何真实 3D API 服务。
        </div>

        <div className="spec-field">
          <label>外部 3D Provider（预留）</label>
          <div style={{ fontSize: 11.5, color: 'var(--accent)', marginBottom: 8 }}>
            {isExternal3DReserved() ? external3DReservedNotice() : ''}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-dim)', marginBottom: 10, lineHeight: 1.5 }}>
            {external3DDisabledReason()}
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 11.5, color: 'var(--text-dim)', width: 74 }}>enabled</span>
            <input
              type="checkbox"
              checked={external3d.enabled}
              onChange={(e) => setExternal3D({ enabled: e.target.checked })}
            />
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 11.5, color: 'var(--text-dim)', width: 74 }}>providerId</span>
            <input
              value={external3d.providerId}
              placeholder="external-3d"
              onChange={(e) => setExternal3D({ providerId: e.target.value })}
            />
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 11.5, color: 'var(--text-dim)', width: 74 }}>baseUrl</span>
            <input
              value={external3d.baseUrl}
              placeholder="https://…（仅格式校验，不联网）"
              onChange={(e) => setExternal3D({ baseUrl: e.target.value })}
            />
          </div>

          {issues.length > 0 && (
            <div style={{ fontSize: 11, color: 'var(--warning)', marginTop: 8, lineHeight: 1.5 }}>
              {issues.map((it) => `${it.field}: ${it.message}`).join('；')}
            </div>
          )}
        </div>

        <div style={{ marginTop: 14, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn btn--ghost" onClick={close}>
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
