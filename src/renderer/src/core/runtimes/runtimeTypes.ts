/**
 * Multi AI 3D Runtime - frontend types (Phase 1 / 3-C / 3-D).
 * Mirrors backend runtime discovery/status for display purposes.
 * Phase 3-C adds Runtime/Model Package install state + download metadata.
 * Phase 3-D adds independent runtime/model package states, download progress,
 * and license acceptance.
 */

export type RuntimeInstallState = 'discovered' | 'not-installed' | 'partial' | 'installed'

export type PackageInstallState =
  | 'not-installed'
  | 'downloading'
  | 'verifying'
  | 'installed'
  | 'partial'
  | 'failed'
  | 'incompatible'
  | 'ready'

export type PackageKind = 'runtime' | 'model'

export type RuntimeStatus =
  | 'discovered'
  | 'not-installed'
  | 'partial'
  | 'installed'
  | 'incompatible'
  | 'ready'
  | 'running'
  | 'stopped'
  | 'failed'
  | 'downloading'
  | 'verifying'

export interface RuntimeHardwareRequirements {
  requiresGPU: boolean
  minimumVRAMMB: number
  recommendedVRAMMB: number
  minimumRAMMB: number
  supportedOS: string[]
  supportedBackends: string[]
}

export interface RuntimeTextureCapability {
  supported: boolean
  kind: 'none' | 'paint' | 'future'
  notes?: string
}

export interface RuntimeCapabilities {
  supportsCancel: boolean
  supportsProgress: boolean
  supportsResume: boolean
  /** Phase 3-G: texture/paint output capability (absent -> shape-only). */
  texture?: RuntimeTextureCapability
}

export interface RuntimeDownload {
  kind: 'runtime' | 'model'
  url: string
  sha256: string
  sizeBytes: number
  httpAllowed?: boolean
}

/** Phase 3-D: one downloadable file of a Runtime/Model package. */
export interface RuntimeArtifact {
  path: string
  url: string
  sha256: string
  sizeBytes: number
  httpAllowed: boolean
}

/** Phase 3-D: one install unit (runtime code package or model weights package). */
export interface RuntimePackage {
  id: string
  kind: PackageKind
  version: string
  source: string
  sourceUrl: string
  license: string
  notice: string
  installDir: string
  artifacts: RuntimeArtifact[]
}

export interface RuntimeLicenseInfo {
  id: string
  url: string
  modelSource: string
  modelSourceUrl: string
  noticeFile: string
  territoryRestrictions: string
  commercialThreshold: string
  requiresAcceptance?: boolean
}

/** Phase 3-D: per-kind install progress feed from the backend. */
export interface InstallProgressState {
  status: 'idle' | 'downloading' | 'verifying' | 'cancelled' | 'done' | 'failed'
  percent: number
  downloadedBytes: number
  totalBytes: number
  speedBps: number
  etaSeconds: number | null
  error: string
}

export interface InstallProgress {
  runtime: InstallProgressState
  model: InstallProgressState
}

export interface RuntimeMetadata {
  id: string
  name: string
  version: string
  modelVersion: string
  inputTypes: string[]
  outputTypes: string[]
  capabilities: RuntimeCapabilities
  hardware: RuntimeHardwareRequirements
  files: { executable: string; modelPath: string; relativeTo: string; license: string; notice: string }
  license: RuntimeLicenseInfo
}

export interface RuntimeInfo {
  id: string
  name: string
  version: string
  modelVersion: string
  /** Phase 3-I: declared input/output types (e.g. ['image'] -> ['glb']). */
  inputTypes: string[]
  outputTypes: string[]
  installState: RuntimeInstallState
  compatible: boolean
  status: RuntimeStatus
  capabilities: RuntimeCapabilities
  hardwareRequirements: RuntimeHardwareRequirements
  license: RuntimeLicenseInfo
  /** Phase 3-C: official download source + integrity metadata (when declared). */
  download: RuntimeDownload | null
  /** Phase 3-C: Runtime/Model Package install state. */
  packageState: PackageInstallState
  /** Phase 3-D: independent runtime / model package states. */
  runtimePackageState: PackageInstallState
  modelPackageState: PackageInstallState
  /** Phase 3-D: license acceptance + requirement. */
  licenseAccepted: boolean
  licenseRequiresAcceptance: boolean
}

export interface HardwareCapability {
  os: string
  architecture: string
  ramMB: number
  gpuVendor: string
  gpuName: string
  vramMB: number | null
  availableBackends: string[]
  /** Phase 3-I: DXGI PCI ids (honest; null when undetected). */
  gpuVendorId?: number | null
  gpuDeviceId?: number | null
  /** Backends the app can currently drive (extension point for future AMD/Intel). */
  knownBackends?: string[]
}

/** Current user selection (Phase 1: never auto-selected). */
export interface RuntimeSelection {
  providerId: 'embedded-ai-3d'
  runtimeId: string | null
}
