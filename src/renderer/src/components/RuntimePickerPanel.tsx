import { useEffect, useState } from 'react'
import type { HardwareCapability, InstallProgress, RuntimeInfo } from '../core/runtimes/runtimeTypes'
import {
  runtimeInstallLabel,
  runtimeStatusLabel,
  vramText,
  gpuUnknownBlocking,
  runtimeInstallAction,
  downloadSizeText,
  packageKindStateLabel,
  formatBytes,
  formatSpeed,
  formatEta,
  runtimeComponentStatus,
  runtimeReady,
  runtimeLicenseOk,
  runtimeRequiresLicense,
  runtimeTextureStatus,
  activeDownloadKind
} from '../core/runtimes/runtimeManager'

const STATUS_ICON: Record<string, string> = {
  ready: '✓',
  running: '▶',
  installed: '✓',
  partial: '⚠',
  'not-installed': '✕',
  incompatible: '✕',
  stopped: '■',
  failed: '✕',
  discovered: '…',
  downloading: '↓',
  verifying: '…'
}

interface RuntimePickerPanelProps {
  runtimes: RuntimeInfo[]
  hardware: HardwareCapability | null
  selectedRuntimeId: string | null
  onSelect: (runtimeId: string) => void
  onStart: (runtimeId: string) => Promise<{ ok: boolean; error?: string }>
  onStop: (runtimeId: string) => Promise<{ ok: boolean }>
  onInstall?: (runtimeId: string, kind: 'runtime' | 'model') => Promise<{ ok: boolean; status?: string; error?: string }>
  onCancelInstall?: (runtimeId: string, kind: 'runtime' | 'model') => Promise<{ ok: boolean }>
  onAcceptLicense?: (runtimeId: string) => Promise<{ ok: boolean; error?: string }>
  progress?: InstallProgress | null
  busy: boolean
}

/**
 * Phase 2.5 / 3-C / 3-D: AI 3D Runtime selector. Pure UI over backend runtime
 * status. Renderer never spawns processes, touches runtime files, reads tokens,
 * or connects to runtime endpoints directly - all via backend API.
 *
 * Phase 3-D shows the full install UX:
 *   - not installed            -> [安装 Runtime] (license confirmation first)
 *   - downloading              -> progress bar + size + speed + ETA + [取消]
 *   - verifying                -> 正在验证 SHA-256...
 *   - runtime installed only   -> Runtime 已安装 / Model 未安装 + [安装模型]
 *   - both installed           -> checklist (Runtime / Model / License / Hardware)
 *                                 + [接受许可证] (when required) + [选择] (ready only)
 * Texture/Paint stays UNAVAILABLE (FUTURE) - never faked as supported.
 */
export default function RuntimePickerPanel({
  runtimes,
  hardware,
  selectedRuntimeId,
  onSelect,
  onStart,
  onStop,
  onInstall,
  onCancelInstall,
  onAcceptLicense,
  progress,
  busy
}: RuntimePickerPanelProps): JSX.Element {
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [agree, setAgree] = useState<Record<string, boolean>>({})

  useEffect(() => {
    setActionMsg(null)
  }, [runtimes, selectedRuntimeId])

  if (runtimes.length === 0) {
    return (
      <div className="spec-field">
        <label>AI 3D Runtime</label>
        <div className="empty-hint">未发现任何 AI 3D Runtime。后端离线或尚无 manifest。</div>
      </div>
    )
  }

  const gpuText =
    hardware && hardware.gpuVendor !== 'unknown'
      ? `${hardware.gpuName || hardware.gpuVendor} · VRAM ${
          hardware.vramMB == null ? '未知' : `${Math.round(hardware.vramMB / 1024)} GB`
        }`
      : 'GPU 未知（未检测到）'
  const ramText = hardware ? `${Math.round(hardware.ramMB / 1024)} GB RAM` : 'RAM 未知'

  const activeKinds = activeDownloadKind(progress)

  const renderLicenseSummary = (r: RuntimeInfo): JSX.Element => (
    <div style={{ fontSize: 10.5, color: 'var(--text-faint)', lineHeight: 1.5 }}>
      <div>许可：{r.license.id || '未标注'}</div>
      {r.license.modelSource ? <div>模型来源：{r.license.modelSource}</div> : null}
      {r.license.modelSourceUrl ? <div>官方源：{r.license.modelSourceUrl}</div> : null}
      {r.license.url ? <div>许可全文：{r.license.url}</div> : null}
      {r.license.territoryRestrictions ? <div>地域限制：{r.license.territoryRestrictions}</div> : null}
      {r.license.commercialThreshold ? <div>商业使用：{r.license.commercialThreshold}</div> : null}
      <div>相关 LICENSE / NOTICE 已随安装包保存，安装前请确认。</div>
    </div>
  )

  const renderChecklist = (comp: ReturnType<typeof runtimeComponentStatus>): JSX.Element => (
    <div style={{ fontSize: 11, lineHeight: 1.7, marginBottom: 4 }}>
      <div style={{ color: comp.runtime ? 'var(--success)' : 'var(--danger)' }}>
        {comp.runtime ? '✓ Runtime' : '✕ Runtime 未安装'}
      </div>
      <div style={{ color: comp.model ? 'var(--success)' : 'var(--danger)' }}>
        {comp.model ? '✓ Model' : '✕ Model 未安装'}
      </div>
      <div style={{ color: comp.license ? 'var(--success)' : 'var(--danger)' }}>
        {comp.license ? '✓ License' : '✕ 许可证未接受'}
      </div>
      <div style={{ color: comp.hardware ? 'var(--success)' : 'var(--danger)' }}>
        {comp.hardware ? '✓ Hardware compatible' : '✕ 硬件不兼容（需要 NVIDIA CUDA GPU，最低 6GB VRAM）'}
      </div>
    </div>
  )

  return (
    <div className="spec-field">
      <label>AI 3D Runtime</label>
      <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 8, lineHeight: 1.5 }}>
        本机硬件：{gpuText} · {ramText}
        {hardware && (
          <span>
            {' '}
            · {hardware.os}/{hardware.architecture}
          </span>
        )}
      </div>

      {runtimes.map((r) => {
        const gpuBlocked = r.hardwareRequirements.requiresGPU && gpuUnknownBlocking(r, hardware?.gpuVendor ?? 'unknown', hardware?.vramMB ?? null)
        const installed = r.installState === 'installed'
        const rtState = r.runtimePackageState
        const mdState = r.modelPackageState
        const comp = runtimeComponentStatus(r)
        const licenseOk = runtimeLicenseOk(r)
        const ready = runtimeReady(r)
        const blockedReason = gpuBlocked
          ? '当前 GPU 不满足要求'
          : !installed
            ? rtState === 'not-installed' && mdState === 'not-installed'
              ? 'Runtime 未安装'
              : 'Runtime 部分安装'
            : !r.compatible
              ? 'Runtime 与当前硬件不兼容'
              : !licenseOk
                ? '尚未接受许可证'
                : null

        const rtActive = rtState === 'downloading' || rtState === 'verifying'
        const mdActive = mdState === 'downloading' || mdState === 'verifying'
        const downloading = rtActive || mdActive
        const kindDownloading: 'runtime' | 'model' = rtActive ? 'runtime' : 'model'
        const progressState = activeKinds?.find((a) => a.kind === kindDownloading)
        const isVerifying = progressState?.status === 'verifying' || rtState === 'verifying' || mdState === 'verifying'
        const prog = progressState && progress ? progress[kindDownloading] : null
        const needLicenseConfirm = runtimeRequiresLicense(r) && !licenseOk

        return (
          <div
            key={r.id}
            style={{
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: 10,
              marginBottom: 8,
              background: selectedRuntimeId === r.id ? 'rgba(108,140,255,0.08)' : 'var(--bg-elevated)'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={{ fontWeight: 600, fontSize: 12.5 }}>
                {r.name}
                <span style={{ color: 'var(--text-faint)', fontWeight: 400, marginLeft: 6 }}>v{r.version}</span>
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                <span
                  style={{
                    color:
                      r.status === 'ready' || r.status === 'running' || r.status === 'installed'
                        ? 'var(--success)'
                        : r.status === 'incompatible' || r.status === 'failed' || r.status === 'not-installed'
                          ? 'var(--danger)'
                          : 'var(--warning)'
                  }}
                >
                  {STATUS_ICON[r.status] ?? '?'}
                </span>{' '}
                {runtimeStatusLabel(r)}（{runtimeInstallLabel(r)}）
              </span>
            </div>

            <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.6, marginBottom: 6 }}>
              模型：{r.modelVersion || '未知'} · 输入 {(r.inputTypes ?? []).join('/') || '未知'} → 输出 {(r.outputTypes ?? []).join('/') || '未知'} ·{' '}
              {r.capabilities?.supportsProgress ? '支持进度' : '无进度'}
              <br />
              硬件：{vramText(r.hardwareRequirements.minimumVRAMMB, r.hardwareRequirements.recommendedVRAMMB)} ·{' '}
              {Math.round(r.hardwareRequirements.minimumRAMMB / 1024)} GB RAM ·{' '}
              {r.hardwareRequirements.requiresGPU ? `需 GPU（${(r.hardwareRequirements.supportedBackends ?? []).join(', ') || '未知 backend'}）` : 'CPU 可运行'}
              <br />
              OS：{(r.hardwareRequirements.supportedOS ?? []).join(', ') || '未知'}
            </div>

            <div style={{ fontSize: 10.5, color: 'var(--text-faint)', marginBottom: 4, lineHeight: 1.5 }}>
              包状态：Runtime {packageKindStateLabel(rtState)} · Model {packageKindStateLabel(mdState)}
              {r.download ? ` · 模型包体积 ${downloadSizeText(r.download.sizeBytes)}` : ''}
            </div>

            {(() => {
              const tex = runtimeTextureStatus(r)
              return (
                <div
                  style={{
                    fontSize: 10.5,
                    marginBottom: 4,
                    color: tex.available ? 'var(--success)' : 'var(--text-faint)'
                  }}
                >
                  {tex.label}
                  {tex.notes ? ` · ${tex.notes}` : ''}
                </div>
              )
            })()}

            {downloading ? (
              <div style={{ marginTop: 6, fontSize: 11 }}>
                {isVerifying ? (
                  <div style={{ color: 'var(--warning)' }}>
                    正在验证 SHA-256...（{packageKindStateLabel(kindDownloading === 'runtime' ? rtState : mdState)}）
                  </div>
                ) : (
                  <>
                    <div
                      style={{
                        height: 8,
                        borderRadius: 4,
                        background: 'var(--bg-elevated)',
                        border: '1px solid var(--border)',
                        overflow: 'hidden',
                        marginBottom: 4
                      }}
                    >
                      <div
                        style={{
                          height: '100%',
                          width: `${Math.max(0, Math.min(100, prog?.percent ?? 0))}%`,
                          background: 'var(--accent)',
                          transition: 'width 0.3s'
                        }}
                      />
                    </div>
                    <div style={{ color: 'var(--text-dim)', lineHeight: 1.5 }}>
                      {prog ? `${prog.percent.toFixed(0)}% · ${formatBytes(prog.downloadedBytes)} / ${formatBytes(prog.totalBytes)}` : '正在连接…'}
                      <br />
                      速度 {prog ? formatSpeed(prog.speedBps) : '—'} · 预计剩余 {prog ? formatEta(prog.etaSeconds) : '—'}
                    </div>
                  </>
                )}
                {onCancelInstall && (
                  <button
                    className="btn btn--sm"
                    style={{ marginTop: 6, color: 'var(--danger)' }}
                    onClick={async () => {
                      await onCancelInstall(r.id, kindDownloading)
                      setActionMsg('已请求取消下载')
                    }}
                  >
                    取消
                  </button>
                )}
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4, flexWrap: 'wrap' }}>
                {!comp.runtime && (
                  <>
                    {needLicenseConfirm && (
                      <label style={{ fontSize: 10.5, color: 'var(--text-dim)', display: 'block', width: '100%' }}>
                        <input
                          type="checkbox"
                          checked={agree[r.id] ?? false}
                          onChange={(e) => setAgree((m) => ({ ...m, [r.id]: e.target.checked }))}
                        />{' '}
                        我已阅读并同意 {r.license.id || '该许可证'}（含地域限制与商业条款）
                      </label>
                    )}
                    {onInstall && (
                      <button
                        className="btn btn--sm btn--primary"
                        disabled={busy || (needLicenseConfirm && !(agree[r.id] ?? false))}
                        title={needLicenseConfirm && !(agree[r.id] ?? false) ? '请先阅读并勾选同意许可证' : undefined}
                        onClick={async () => {
                          setActionMsg('开始安装 Runtime…')
                          const res = await onInstall(r.id, 'runtime')
                          setActionMsg(res.ok ? '已开始安装' : res.error ?? '安装失败')
                        }}
                      >
                        {runtimeInstallAction(r)}
                      </button>
                    )}
                  </>
                )}
                {comp.runtime && !comp.model && (
                  <>
                    <span style={{ fontSize: 11, color: 'var(--warning)' }}>Runtime 已安装 / Model 未安装</span>
                    {onInstall && (
                      <button
                        className="btn btn--sm btn--primary"
                        disabled={busy}
                        onClick={async () => {
                          setActionMsg('开始安装模型…')
                          const res = await onInstall(r.id, 'model')
                          setActionMsg(res.ok ? '已开始安装' : res.error ?? '安装失败')
                        }}
                      >
                        安装模型
                      </button>
                    )}
                  </>
                )}
                {comp.runtime && comp.model && (
                  <>
                    {renderChecklist(comp)}
                    {!licenseOk && onAcceptLicense && (
                      <>
                        {renderLicenseSummary(r)}
                        <button
                          className="btn btn--sm btn--primary"
                          disabled={busy}
                          style={{ marginTop: 4 }}
                          onClick={async () => {
                            const res = await onAcceptLicense(r.id)
                            setActionMsg(res.ok ? '已接受许可证' : res.error ?? '接受失败')
                          }}
                        >
                          接受并同意许可证
                        </button>
                      </>
                    )}
                    {ready && (
                      <button
                        className="btn btn--sm btn--primary"
                        onClick={() => {
                          onSelect(r.id)
                          setActionMsg(null)
                        }}
                      >
                        选择
                      </button>
                    )}
                    {comp.runtime && comp.model && !ready && blockedReason && (
                      <span style={{ fontSize: 11, color: 'var(--warning)' }}>✕ {blockedReason}</span>
                    )}
                    {(r.status === 'ready' || r.status === 'stopped') && !busy && installed && (
                      <button
                        className="btn btn--sm"
                        onClick={async () => {
                          const res = await onStart(r.id)
                          setActionMsg(res.ok ? '已启动' : res.error ?? '启动失败')
                        }}
                      >
                        启动
                      </button>
                    )}
                    {r.status === 'running' && (
                      <button
                        className="btn btn--sm"
                        onClick={async () => {
                          await onStop(r.id)
                          setActionMsg('已停止')
                        }}
                      >
                        停止
                      </button>
                    )}
                  </>
                )}
              </div>
            )}

            {r.license && (r.license.id || r.license.url) && !downloading && (
              <div style={{ fontSize: 10.5, color: 'var(--text-faint)', marginTop: 6, lineHeight: 1.5 }}>
                许可：{r.license.id || '未标注'}
                {r.license.modelSource ? ` · 模型来源：${r.license.modelSource}` : ''}
                {r.license.territoryRestrictions ? ` · ${r.license.territoryRestrictions}` : ''}
                {r.license.commercialThreshold ? ` · ${r.license.commercialThreshold}` : ''}
              </div>
            )}

            {selectedRuntimeId === r.id && !ready && blockedReason && (
              <div style={{ fontSize: 11, color: 'var(--warning)', marginTop: 6 }}>无法生成：{blockedReason}</div>
            )}
          </div>
        )
      })}

      {actionMsg && <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>{actionMsg}</div>}
    </div>
  )
}
