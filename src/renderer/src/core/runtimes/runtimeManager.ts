import type { PackageInstallState, RuntimeInfo, RuntimeMetadata } from './runtimeTypes'

/**
 * Multi AI 3D Runtime - pure frontend logic (Phase 1 / 3-C / 3-D).
 * Derives display state from backend runtime discovery. No network, no real
 * runtime. A runtime can be installed=true AND compatible=false (hardware).
 */

export function runtimeInstallLabel(r: RuntimeInfo): string {
  switch (r.installState) {
    case 'installed':
      return '已安装'
    case 'partial':
      return '部分安装'
    case 'not-installed':
      return '未安装'
    default:
      return '已发现'
  }
}

export function runtimeStatusLabel(r: RuntimeInfo): string {
  switch (r.status) {
    case 'ready':
      return '可用'
    case 'running':
      return '运行中'
    case 'stopped':
      return '运行结束'
    case 'incompatible':
      return '硬件不兼容'
    case 'failed':
      return '运行失败'
    case 'partial':
      return '部分安装'
    case 'not-installed':
      return '未安装'
    case 'installed':
      return '已安装'
    default:
      return '已发现'
  }
}

/** Whether the runtime is selectable for generation (installed + compatible). */
export function runtimeSelectable(r: RuntimeInfo): boolean {
  return r.installState === 'installed' && r.compatible
}

/** Human-readable VRAM requirement. */
export function vramText(min: number, recommended: number): string {
  return `最低 ${min / 1024} GB / 推荐 ${recommended / 1024} GB`
}

/** True when the runtime requires GPU but detection returned unknown. */
export function gpuUnknownBlocking(r: RuntimeInfo, gpuVendor: string, vramMB: number | null): boolean {
  if (!r.hardwareRequirements.requiresGPU) return false
  return gpuVendor === 'unknown' || vramMB === null || vramMB < r.hardwareRequirements.minimumVRAMMB
}

/** Phase 3-C: install/download button action label. */
export function runtimeInstallAction(r: RuntimeInfo): string {
  if (r.packageState === 'downloading') return '下载中…'
  if (r.packageState === 'verifying') return '校验中…'
  if (r.installState === 'installed') return '已安装'
  if (r.installState === 'partial') return '继续安装'
  return '安装 Runtime'
}

/** Phase 3-C: package state label (Chinese). */
export function packageStateLabel(r: RuntimeInfo): string {
  switch (r.packageState) {
    case 'installed':
    case 'ready':
      return '已安装'
    case 'downloading':
      return '下载中'
    case 'verifying':
      return '校验中'
    case 'partial':
      return '部分安装'
    case 'failed':
      return '安装失败'
    case 'incompatible':
      return '硬件不兼容'
    default:
      return '未安装'
  }
}

/** Phase 3-C: human-readable download size (GB). */
export function downloadSizeText(sizeBytes: number | null | undefined): string {
  if (!sizeBytes || sizeBytes <= 0) return '体积未知'
  return `${(sizeBytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

// ---- Phase 3-D: independent package states + license gating + progress ----

/** Chinese label for ONE package kind's install state. */
export function packageKindStateLabel(state: PackageInstallState | string): string {
  switch (state) {
    case 'installed':
    case 'ready':
      return '已安装'
    case 'downloading':
      return '下载中'
    case 'verifying':
      return '校验中'
    case 'partial':
      return '部分安装'
    case 'failed':
      return '安装失败'
    case 'incompatible':
      return '硬件不兼容'
    default:
      return '未安装'
  }
}

/** Human-readable byte size (adaptive unit). */
export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '0 B'
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

/** Human-readable download speed (bytes/second). */
export function formatSpeed(bps: number | null | undefined): string {
  if (!bps || bps <= 0) return '—'
  if (bps >= 1024 * 1024) return `${(bps / 1024 / 1024).toFixed(1)} MB/s`
  if (bps >= 1024) return `${(bps / 1024).toFixed(1)} KB/s`
  return `${Math.round(bps)} B/s`
}

/** Human-readable ETA (seconds). */
export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds) || seconds < 0) return '—'
  if (seconds < 60) return `剩余 ${Math.ceil(seconds)} 秒`
  const m = Math.floor(seconds / 60)
  const s = Math.ceil(seconds % 60)
  if (m < 60) return `剩余 ${m} 分 ${s} 秒`
  return `剩余 ${Math.floor(m / 60)} 小时 ${m % 60} 分`
}

/** True when the runtime license has been accepted (or is not required). */
export function runtimeLicenseOk(r: RuntimeInfo): boolean {
  return !r.licenseRequiresAcceptance || r.licenseAccepted === true
}

/** True when the runtime requires the user to accept a license. */
export function runtimeRequiresLicense(r: RuntimeInfo): boolean {
  return r.licenseRequiresAcceptance !== false && Boolean(r.license?.id)
}

/** Checklist of independent install components (Phase 3-D UI). */
export function runtimeComponentStatus(r: RuntimeInfo): {
  runtime: boolean
  model: boolean
  license: boolean
  hardware: boolean
} {
  return {
    runtime: r.runtimePackageState === 'installed',
    model: r.modelPackageState === 'installed',
    license: runtimeLicenseOk(r),
    hardware: r.compatible === true
  }
}

/** True when generation may proceed: both packages + license + hardware. */
export function runtimeReady(r: RuntimeInfo): boolean {
  return (
    r.runtimePackageState === 'installed' &&
    r.modelPackageState === 'installed' &&
    runtimeLicenseOk(r) &&
    r.compatible === true
  )
}

export interface ActiveDownload {
  kind: 'runtime' | 'model'
  status: string
}

/** Phase 3-G/3-H: texture/paint output status, driven by the manifest capability
 * AND the runtime install state (a declared capability is never claimed as
 * available before the runtime is installed + compatible). */
export function runtimeTextureStatus(r: RuntimeInfo): {
  supported: boolean
  available: boolean
  kind: string
  label: string
  notes?: string
} {
  const t = r.capabilities?.texture
  const installed = r.installState === 'installed'
  if (t?.supported) {
    if (installed && r.compatible) {
      return { supported: true, available: true, kind: t.kind ?? 'paint', label: '支持贴图输出（mesh + texture）', notes: t?.notes }
    }
    if (!installed) {
      return {
        supported: true,
        available: false,
        kind: t.kind ?? 'paint',
        label: 'Texture/Paint：未安装（需安装 Texture/Paint Runtime）',
        notes: t?.notes
      }
    }
    return {
      supported: true,
      available: false,
      kind: t.kind ?? 'paint',
      label: 'Texture/Paint：硬件不满足（需要 NVIDIA CUDA GPU / 16 GB VRAM）',
      notes: t?.notes
    }
  }
  const kind = t?.kind ?? 'none'
  const label = kind === 'future' ? 'Shape only · Texture/Paint unavailable (future)' : 'Shape only'
  return { supported: false, available: false, kind, label, notes: t?.notes }
}

/** Per-kind download state (used to render the progress bar / cancel button). */
export function activeDownloadKind(
  progress: { runtime?: { status: string }; model?: { status: string } } | null | undefined
): ActiveDownload[] | null {
  if (!progress) return null
  const out: ActiveDownload[] = []
  for (const kind of ['runtime', 'model'] as const) {
    const st = progress[kind]
    if (st && (st.status === 'downloading' || st.status === 'verifying')) out.push({ kind, status: st.status })
  }
  return out.length > 0 ? out : null
}

/** Build a stable id (kept pure; not used for generation). */
export function selectionForRuntime(runtimeId: string): { providerId: 'embedded-ai-3d'; runtimeId: string } {
  return { providerId: 'embedded-ai-3d', runtimeId }
}

/** Normalize a raw backend runtime entry into RuntimeInfo (defensive). */
export function normalizeRuntimeInfo(raw: Partial<RuntimeInfo>): RuntimeInfo | null {
  if (!raw.id) return null
  return {
    id: raw.id,
    name: raw.name ?? raw.id,
    version: raw.version ?? '',
    modelVersion: raw.modelVersion ?? '',
    installState: raw.installState ?? 'discovered',
    compatible: raw.compatible ?? false,
    status: raw.status ?? 'discovered',
    capabilities: raw.capabilities ?? { supportsCancel: false, supportsProgress: false, supportsResume: false },
    hardwareRequirements: raw.hardwareRequirements ?? {
      requiresGPU: true,
      minimumVRAMMB: 0,
      recommendedVRAMMB: 0,
      minimumRAMMB: 0,
      supportedOS: [],
      supportedBackends: []
    },
    license: {
      id: '',
      url: '',
      modelSource: '',
      modelSourceUrl: '',
      noticeFile: '',
      territoryRestrictions: '',
      commercialThreshold: '',
      requiresAcceptance: true,
      ...(raw.license ?? {})
    },
    download: raw.download ?? null,
    inputTypes: raw.inputTypes ?? [],
    outputTypes: raw.outputTypes ?? [],
    packageState: raw.packageState ?? (raw.installState === 'installed' ? 'ready' : 'not-installed'),
    runtimePackageState: raw.runtimePackageState ?? (raw.installState === 'installed' ? 'installed' : 'not-installed'),
    modelPackageState: raw.modelPackageState ?? (raw.installState === 'installed' ? 'installed' : 'not-installed'),
    licenseAccepted: raw.licenseAccepted ?? false,
    licenseRequiresAcceptance: raw.licenseRequiresAcceptance ?? (raw.license?.id ? true : false)
  }
}

/** True when the given raw metadata maps to a usable runtime (no download). */
export function metadataUsable(m: RuntimeMetadata | null | undefined): boolean {
  if (!m) return false
  return Boolean(m.id && m.files.executable && m.files.modelPath)
}
