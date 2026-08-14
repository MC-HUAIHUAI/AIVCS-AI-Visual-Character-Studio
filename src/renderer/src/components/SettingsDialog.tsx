import { useEffect, useState } from 'react'
import { useUIStore } from '../store/uiStore'
import {
  providerStatus,
  redactApiKey,
  validateAppSettings
} from '../core/settings/appSettingsLogic'
import { external3DDisabledReason } from '../core/settings/external3dSettingsLogic'
import type { ProviderEndpointSettings } from '@shared/types'

const STATUS_LABEL = {
  unconfigured: '未配置',
  'configured-disabled': '已配置未启用',
  enabled: '已启用'
}

interface ProviderRowProps {
  title: string
  hint: string
  value: ProviderEndpointSettings
  onChange: (patch: Partial<ProviderEndpointSettings>) => void
  onTest: () => Promise<{ ok: boolean; error?: string }>
  unavailable?: boolean
}

function ProviderRow({ title, hint, value, onChange, onTest, unavailable }: ProviderRowProps): JSX.Element {
  const [showKey, setShowKey] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)
  const status = providerStatus(value)
  const statusColor = status === 'enabled' ? 'var(--success)' : status === 'configured-disabled' ? 'var(--warning)' : 'var(--text-faint)'

  const runTest = async (): Promise<void> => {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await onTest()
      setTestResult(r.ok ? '连接成功' : r.error ?? '连接失败')
    } finally {
      setTesting(false)
    }
  }

  const row = (label: string, children: JSX.Element, extra?: JSX.Element): JSX.Element => (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
      <span style={{ fontSize: 11.5, color: 'var(--text-dim)', width: 74, flexShrink: 0 }}>{label}</span>
      {children}
      {extra}
    </div>
  )

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10, marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>{title}</span>
        <span style={{ fontSize: 11, color: statusColor }}>{STATUS_LABEL[status]}</span>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 10, lineHeight: 1.5 }}>{hint}</div>

      {row(
        'enabled',
        <input type="checkbox" checked={value.enabled} onChange={(e) => onChange({ enabled: e.target.checked })} />
      )}
      {row('providerId', <input value={value.providerId} placeholder="kimi / external-3d" onChange={(e) => onChange({ providerId: e.target.value })} />)}
      {row('baseUrl', <input value={value.baseUrl} placeholder="https://…" onChange={(e) => onChange({ baseUrl: e.target.value })} />)}
      {row(
        'apiKey',
        <input
          type={showKey ? 'text' : 'password'}
          value={value.apiKey}
          placeholder="仅保存在本机（safeStorage）"
          onChange={(e) => onChange({ apiKey: e.target.value })}
          style={{ flex: 1 }}
        />,
        <button
          className="btn btn--sm"
          onClick={() => setShowKey((v) => !v)}
          title={showKey ? '隐藏 API Key' : '显示 API Key'}
        >
          {showKey ? '隐藏' : '显示'}
        </button>
      )}
      {value.apiKey && (
        <div style={{ fontSize: 10.5, color: 'var(--text-faint)', marginBottom: 8 }}>
          当前已填（脱敏显示）：{redactApiKey(value.apiKey)}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
        <button className="btn btn--sm" disabled={testing || unavailable} onClick={() => void runTest()}>
          {testing ? '测试中…' : '测试连接'}
        </button>
        {testResult && <span style={{ fontSize: 11, color: testResult === '连接成功' ? 'var(--success)' : 'var(--danger)' }}>{testResult}</span>}
      </div>
      {unavailable && (
        <div style={{ fontSize: 11, color: 'var(--warning)', marginTop: 8, lineHeight: 1.5 }}>{external3DDisabledReason()}</div>
      )}
    </div>
  )
}

/**
 * Phase 3-5A: app-level provider settings dialog.
 * Startup/load/save are network-free; only an explicit "test connection" click
 * may contact an endpoint.
 */
export default function SettingsDialog(): JSX.Element {
  const open = useUIStore((s) => s.settingsOpen)
  const close = useUIStore((s) => s.closeSettings)
  const appSettings = useUIStore((s) => s.appSettings)
  const setVisionSettings = useUIStore((s) => s.setVisionSettings)
  const setExternal3D = useUIStore((s) => s.setExternal3D)
  const loadAppSettings = useUIStore((s) => s.loadAppSettings)
  const saveAppSettings = useUIStore((s) => s.saveAppSettings)
  const testProviderConnection = useUIStore((s) => s.testProviderConnection)

  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (open) void loadAppSettings()
  }, [open, loadAppSettings])

  if (!open) return <></>

  const issues = validateAppSettings(appSettings)

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
    width: 520,
    maxWidth: '92vw',
    maxHeight: '90vh',
    overflowY: 'auto',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    borderRadius: 12,
    padding: 18,
    boxShadow: '0 12px 40px rgba(0,0,0,0.5)'
  }

  const handleSave = async (): Promise<void> => {
    const r = await saveAppSettings()
    setSaved(r.ok)
  }

  return (
    <div style={overlayStyle} onClick={close}>
      <div style={boxStyle} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>设置</div>
        <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 14, lineHeight: 1.6 }}>
          软件默认无需任何 API 即可运行；API 为可选增强能力。设置仅在保存时写入本机，绝不进入项目数据。
        </div>

        <ProviderRow
          title="Vision Provider"
          hint="配置后使用真实视觉理解（如 Kimi）；未配置时使用本地 Mock，零联网。"
          value={appSettings.vision}
          onChange={setVisionSettings}
          onTest={() => testProviderConnection('vision')}
        />

        <ProviderRow
          title="外部 3D Provider"
          hint="已预留配置；真实外部 3D 服务尚未实现，本阶段继续使用本地 LocalLowPower / Mock。"
          value={appSettings.external3d}
          onChange={setExternal3D}
          onTest={() => testProviderConnection('external3d')}
          unavailable
        />

        {issues.length > 0 && (
          <div style={{ fontSize: 11, color: 'var(--warning)', marginTop: 8, lineHeight: 1.5 }}>
            {issues.map((it) => `${it.section}.${it.field}: ${it.message}`).join('；')}
          </div>
        )}

        <div style={{ marginTop: 14, display: 'flex', justifyContent: 'flex-end', gap: 8, alignItems: 'center' }}>
          {saved && <span style={{ fontSize: 11, color: 'var(--success)' }}>已保存</span>}
          <button className="btn btn--primary" onClick={() => void handleSave()}>
            保存设置
          </button>
          <button className="btn btn--ghost" onClick={close}>
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
