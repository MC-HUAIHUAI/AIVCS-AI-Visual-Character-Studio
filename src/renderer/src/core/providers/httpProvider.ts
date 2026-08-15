import type { AIImage3DProvider, GeneratedModelResult, GenerationProgress } from './aiProvider'
import type { GenerationAbortSignal } from './aiProvider'
import type { CharacterAsset, CharacterSpec, GlbStats, ModelFormat } from '@shared/types'
import type { VisionImageInput } from './visionProvider'
import type { HardwareCapability, InstallProgress, RuntimeInfo } from '../runtimes/runtimeTypes'
import type { GenerationRequest, JobDto } from '../spec/generationLogic'
import { isTerminal, safeErrorMessage } from '../spec/generationLogic'

export const AIVCS_BACKEND_URL = 'http://127.0.0.1:8321'

export const DEFAULT_GENERATION_TIMEOUT_SECONDS = 600

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

export async function backendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/health`, { signal: AbortSignal.timeout(2500) })
    return res.ok
  } catch {
    return false
  }
}

export interface ProviderStatusInfo {
  id: string
  available: boolean
  capability: {
    mode: string
    gpuRequired: boolean
    maxReferences: number
    outputFormat: string
    supportsCancel: boolean
    supportsTimeout: boolean
    kind: string
  } | null
}

/** Reads provider availability + capability metadata from the local backend (no key). */
export async function fetchProviderStatus(): Promise<ProviderStatusInfo[]> {
  const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/providers`, { signal: AbortSignal.timeout(2500) })
  if (!res.ok) return []
  return (await res.json()) as ProviderStatusInfo[]
}

/** Reads discovered AI 3D runtimes from the backend (no key, no spawn). */
export async function fetchRuntimes(): Promise<RuntimeInfo[]> {
  const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/runtime`, { signal: AbortSignal.timeout(2500) })
  if (!res.ok) return []
  const body = (await res.json()) as { runtimes: RuntimeInfo[] }
  return body.runtimes ?? []
}

export interface Ai3dSettings {
  installBase: string
  modelsDir: string
  runtimesDir: string
  manifestsDir: string
  allowDownload: boolean
  allowDownloadEnv: string
  userDataEnv?: string | null
  manifestsDirEnv?: string | null
  pythonInterpreter?: string
}

/** Phase 3-I: read-only AI 3D settings for the Settings UI (no tokens/secrets). */
export async function fetchAi3dSettings(): Promise<Ai3dSettings | null> {
  try {
    const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/ai3d/settings`, { signal: AbortSignal.timeout(2500) })
    if (!res.ok) return null
    return (await res.json()) as Ai3dSettings
  } catch {
    return null
  }
}

/** Reads backend hardware capability (unknown-safe). */
export async function fetchHardware(): Promise<HardwareCapability | null> {
  try {
    const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/system/hardware`, { signal: AbortSignal.timeout(2500) })
    if (!res.ok) return null
    return (await res.json()) as HardwareCapability
  } catch {
    return null
  }
}

/** Starts a runtime process (backend-managed). */
export async function startRuntime(runtimeId: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/runtime/${encodeURIComponent(runtimeId)}/start`, {
      method: 'POST',
      signal: AbortSignal.timeout(20000)
    })
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string }
      return { ok: false, error: body.detail ?? `HTTP ${res.status}` }
    }
    return { ok: true }
  } catch {
    return { ok: false, error: '后端离线，无法启动 Runtime' }
  }
}

/** Stops a runtime process (backend-managed). */
export async function stopRuntime(runtimeId: string): Promise<{ ok: boolean }> {
  try {
    const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/runtime/${encodeURIComponent(runtimeId)}/stop`, {
      method: 'POST',
      signal: AbortSignal.timeout(10000)
    })
    return { ok: res.ok }
  } catch {
    return { ok: false }
  }
}

/** Reads runtime process status (install + compat + process). */
export async function fetchRuntimeStatus(runtimeId: string): Promise<{ ok: boolean; status?: string; error?: string }> {
  try {
    const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/runtime/${encodeURIComponent(runtimeId)}/status`, {
      signal: AbortSignal.timeout(2500)
    })
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` }
    return (await res.json()) as { ok: boolean; status?: string; error?: string }
  } catch {
    return { ok: false, error: '后端离线' }
  }
}

/** Phase 3-D: begin the package install state machine for one kind (background
 * thread). Real network downloads are disabled by default; the backend returns
 * an explicit NOT_INSTALLED result so the UI never shows a fake success. */
export async function installRuntime(
  runtimeId: string,
  kind: 'runtime' | 'model' | 'all' = 'runtime'
): Promise<{ ok: boolean; started?: boolean; error?: string }> {
  try {
    const res = await fetch(
      `${AIVCS_BACKEND_URL}/api/v1/runtime/${encodeURIComponent(runtimeId)}/install?kind=${encodeURIComponent(kind)}`,
      { method: 'POST', signal: AbortSignal.timeout(15000) }
    )
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string }
      return { ok: false, error: body.detail ?? `HTTP ${res.status}` }
    }
    return (await res.json()) as { ok: boolean; started?: boolean; error?: string }
  } catch {
    return { ok: false, error: '后端离线，无法开始安装' }
  }
}

/** Phase 3-D: request cancellation of an in-flight package download. */
export async function cancelRuntimeInstall(
  runtimeId: string,
  kind: 'runtime' | 'model' = 'runtime'
): Promise<{ ok: boolean; cancelled?: boolean }> {
  try {
    const res = await fetch(
      `${AIVCS_BACKEND_URL}/api/v1/runtime/${encodeURIComponent(runtimeId)}/install/cancel?kind=${encodeURIComponent(kind)}`,
      { method: 'POST', signal: AbortSignal.timeout(10000) }
    )
    if (!res.ok) return { ok: false }
    return (await res.json()) as { ok: boolean; cancelled?: boolean }
  } catch {
    return { ok: false }
  }
}

/** Phase 3-D: per-kind install progress (percent / size / speed / ETA). */
export async function fetchInstallProgress(runtimeId: string): Promise<InstallProgress | null> {
  try {
    const res = await fetch(
      `${AIVCS_BACKEND_URL}/api/v1/runtime/${encodeURIComponent(runtimeId)}/install/progress`,
      { signal: AbortSignal.timeout(2500) }
    )
    if (!res.ok) return null
    return (await res.json()) as InstallProgress
  } catch {
    return null
  }
}

/** Phase 3-D: record explicit license acceptance (required before start). */
export async function acceptRuntimeLicense(
  runtimeId: string,
  accepted = true
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(
      `${AIVCS_BACKEND_URL}/api/v1/runtime/${encodeURIComponent(runtimeId)}/license/accept`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accepted }),
        signal: AbortSignal.timeout(10000)
      }
    )
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string }
      return { ok: false, error: body.detail ?? `HTTP ${res.status}` }
    }
    return (await res.json()) as { ok: boolean; error?: string }
  } catch {
    return { ok: false, error: '后端离线，无法保存许可证确认' }
  }
}

export interface CreateGenerationRequest {
  backendProviderId?: string
  spec: CharacterSpec
  references: GenerationRequest['references']
  timeoutSeconds?: number
  /** Phase 3-3: optional render-layer (derived CharacterAsset). */
  characterAsset?: CharacterAsset
  /** Phase 3-C: optional explicit embedded runtime selection. */
  runtimeId?: string | null
}

export async function createGenerationJob(req: CreateGenerationRequest): Promise<{ jobId: string }> {
  const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/generate/image-to-3d`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider: req.backendProviderId ?? 'mock',
      spec: req.spec,
      references: req.references,
      timeoutSeconds: req.timeoutSeconds ?? DEFAULT_GENERATION_TIMEOUT_SECONDS,
      characterAsset: req.characterAsset ?? undefined,
      runtimeId: req.runtimeId ?? undefined
    })
  })
  if (!res.ok) {
    throw new Error(`无法创建生成任务（HTTP ${res.status}）。后端是否已启动？`)
  }
  const data = (await res.json()) as { jobId: string }
  return { jobId: data.jobId }
}

export async function pollGenerationJob(jobId: string): Promise<JobDto> {
  const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/generate/jobs/${jobId}`)
  if (!res.ok) throw new Error(`轮询生成任务失败（HTTP ${res.status}）`)
  return (await res.json()) as JobDto
}

export async function cancelGenerationJob(jobId: string): Promise<boolean> {
  const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/generate/jobs/${jobId}/cancel`, {
    method: 'POST'
  })
  if (!res.ok) throw new Error(`取消失败（HTTP ${res.status}）`)
  const data = (await res.json()) as { cancelled: boolean }
  return data.cancelled
}

export interface RigLocal3dResult {
  ok: boolean
  vrmModelId?: string
  sourceModelId?: string
  format?: string
  error?: string
  classification?: { kind: string; reason: string; skinned: boolean; bodyType?: string | null }
  skeleton?: { boneCount: number; root?: string | null }
  boneMapping?: { requiredCovered: number; requiredTotal: number }
  vrmMeta?: { specVersion?: string; name?: string }
  sourceSkinned?: boolean
  autoRigged?: boolean
  /** Phase 3-J: analyzer stats of the rigged GLB (for the derived VRM model). */
  stats?: GlbStats
}

/** Phase 3-F: run the Local 3D -> VRM Rigging Pipeline over a ModelStore GLB. */
export async function rigLocal3dModel(
  modelId: string,
  opts: { bodyType?: string; characterType?: string; modelName?: string } = {}
): Promise<RigLocal3dResult> {
  try {
    const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/local3d/rig/${encodeURIComponent(modelId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(opts),
      signal: AbortSignal.timeout(30000)
    })
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string }
      return { ok: false, error: body.detail ?? `HTTP ${res.status}` }
    }
    return (await res.json()) as RigLocal3dResult
  } catch {
    return { ok: false, error: '后端离线，无法执行 Rig 管线' }
  }
}

export interface ConvertToVrmResult {
  ok: boolean
  vrmModelId?: string
  bytes?: ArrayBuffer
  classification?: { kind: string; reason: string }
  sourceSkinned?: boolean
  autoRigged?: boolean
  stats?: GlbStats
  error?: string
}

/** Phase 3-J: run the Local 3D -> VRM pipeline over a GLB model and download
 * the resulting VRM. The original GLB is never modified (a new VRM model is
 * persisted). Non-human / unclassified models fail with a clear reason. */
export async function convertModelToVrm(
  modelId: string,
  opts: { bodyType?: string; characterType?: string; modelName?: string } = {}
): Promise<ConvertToVrmResult> {
  const rig = await rigLocal3dModel(modelId, opts)
  if (!rig.ok || !rig.vrmModelId) {
    return { ok: false, error: rig.error ?? 'Rig 失败' }
  }
  try {
    const { bytes } = await downloadModel(rig.vrmModelId)
    return {
      ok: true,
      vrmModelId: rig.vrmModelId,
      bytes,
      classification: rig.classification,
      sourceSkinned: rig.sourceSkinned,
      autoRigged: rig.autoRigged,
      stats: rig.stats
    }
  } catch {
    return { ok: false, error: 'VRM 生成成功但下载失败' }
  }
}

export async function downloadModel(
  modelId: string
): Promise<{ bytes: ArrayBuffer; mime?: string; sizeBytes?: number }> {
  const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/models/${modelId}`, {
    signal: AbortSignal.timeout(30000)
  })
  if (!res.ok) throw new Error(`模型下载失败（HTTP ${res.status}）`)
  const bytes = await res.arrayBuffer()
  return { bytes, mime: res.headers.get('Content-Type') ?? undefined, sizeBytes: bytes.byteLength }
}

export interface VrmFetchError extends Error {
  status: number | null
  detail: string | null
  isNetwork: boolean
}

export async function fetchVrmBytes(
  modelId: string,
  bodyType: string,
  name: string
): Promise<{ bytes: ArrayBuffer; mime: string }> {
  let res: Response
  try {
    res = await fetch(
      `${AIVCS_BACKEND_URL}/api/v1/models/${encodeURIComponent(modelId)}/vrm?body_type=${encodeURIComponent(bodyType)}&name=${encodeURIComponent(name)}`,
      { signal: AbortSignal.timeout(30000) }
    )
  } catch {
    const err = new Error('后端离线，无法导出 VRM') as VrmFetchError
    err.status = null
    err.detail = null
    err.isNetwork = true
    throw err
  }
  if (!res.ok) {
    let detail: string | null = null
    try {
      const body = (await res.json()) as { detail?: string }
      detail = body.detail ?? null
    } catch {
      detail = null
    }
    const err = new Error(`VRM 导出失败（HTTP ${res.status}）`) as VrmFetchError
    err.status = res.status
    err.detail = detail
    err.isNetwork = false
    throw err
  }
  const bytes = await res.arrayBuffer()
  return { bytes, mime: res.headers.get('Content-Type') ?? 'model/gltf-binary' }
}

/** Shared backend job flow used by backend providers (create -> poll -> download). */
async function runBackendGenerate(
  backendProviderId: string,
  spec: CharacterSpec,
  references: VisionImageInput[],
  onProgress: (p: GenerationProgress) => void,
  signal?: GenerationAbortSignal
): Promise<GeneratedModelResult> {
  const created = await createGenerationJob({
    backendProviderId,
    spec,
    references: references.map((r) => ({ imageId: r.imageId, dataUrl: r.dataUrl, view: r.view ?? null })),
    timeoutSeconds: DEFAULT_GENERATION_TIMEOUT_SECONDS
  })

  let dto: JobDto | null = null
  for (;;) {
    dto = await pollGenerationJob(created.jobId)
    onProgress({
      step: dto.steps.filter((s) => s.status === 'done' || s.status === 'running').length,
      totalSteps: dto.steps.length,
      percent: dto.progress,
      message: dto.message
    })
    if (isTerminal(dto.status)) break
    if (signal?.aborted) {
      await cancelGenerationJob(created.jobId)
      throw new Error('generation aborted')
    }
    await sleep(450)
  }
  if (dto && dto.status === 'done' && dto.result?.model_id) {
    const { bytes, mime, sizeBytes } = await downloadModel(dto.result.model_id)
    return {
      modelId: dto.result.model_id,
      name: 'generated_character',
      format: (dto.result.format ?? 'glb') as ModelFormat,
      sizeBytes: dto.result.size_bytes ?? sizeBytes,
      providerId: dto.result.provider_id,
      sourceJobId: dto.result.source_job_id,
      mime: dto.result.mime ?? mime,
      glbStats: dto.result.stats,
      bytes
    }
  }
  if (dto?.status === 'cancelled' || signal?.aborted) {
    throw new Error('generation aborted')
  }
  throw new Error(safeErrorMessage(new Error(dto?.error ?? '生成失败')))
}

/**
 * Job-aware backend provider. The generationStore drives the full job lifecycle
 * (create/poll/cancel/download) through generationApi; this class implements the
 * AIImage3DProvider contract for direct/standalone use with signal support.
 */
export class BackendImage3DProvider implements AIImage3DProvider {
  readonly id = 'backend-fastapi'
  readonly name = 'FastAPI 后端（Mock）'
  readonly description =
    '通过本地 FastAPI 后端运行生成任务（状态机 / 取消 / 超时 / 持久化模型）。需要运行 `npm run backend`。'
  readonly requiresBackend = true
  readonly capabilities = {
    mode: 'cloud' as const,
    gpuRequired: false,
    maxReferences: 4,
    outputFormat: 'glb' as const,
    supportsCancel: true,
    supportsTimeout: true,
    backendId: 'mock',
    kind: 'mock' as const
  }

  async generate(
    spec: CharacterSpec,
    references: VisionImageInput[],
    onProgress: (p: GenerationProgress) => void,
    signal?: GenerationAbortSignal
  ): Promise<GeneratedModelResult> {
    return runBackendGenerate(this.capabilities.backendId, spec, references, onProgress, signal)
  }
}

/**
 * Frontend handle for the backend LocalLowPower3DProvider (CPU, deterministic).
 * The generationStore drives the job lifecycle through capabilities.backendId.
 */
export class LocalLowPower3DProvider implements AIImage3DProvider {
  readonly id = 'backend-local-lowpower'
  readonly name = '本地低功耗 3D（CPU）'
  readonly description =
    '本地 CPU 低功耗确定性原型：由角色设定 + 参考图配色生成低模 GLB。需要运行 `npm run backend`。'
  readonly requiresBackend = true
  readonly capabilities = {
    mode: 'local' as const,
    gpuRequired: false,
    maxReferences: 4,
    outputFormat: 'glb' as const,
    supportsCancel: true,
    supportsTimeout: true,
    backendId: 'local-lowpower',
    kind: 'local' as const
  }

  async generate(
    spec: CharacterSpec,
    references: VisionImageInput[],
    onProgress: (p: GenerationProgress) => void,
    signal?: GenerationAbortSignal
  ): Promise<GeneratedModelResult> {
    return runBackendGenerate(this.capabilities.backendId, spec, references, onProgress, signal)
  }
}

/**
 * Frontend handle for the backend MockRemote3DProvider (simulated vendor
 * "create -> poll -> download" pipeline). Drives the job lifecycle via
 * capabilities.backendId.
 */
export class MockRemote3DProvider implements AIImage3DProvider {
  readonly id = 'backend-mock-remote'
  readonly name = 'Mock Remote（模拟厂商）'
  readonly description =
    '模拟真实厂商的 创建任务→轮询→下载 GLB 流程，无需任何真实 3D API。需要运行 `npm run backend`。'
  readonly requiresBackend = true
  readonly capabilities = {
    mode: 'cloud' as const,
    gpuRequired: false,
    maxReferences: 4,
    outputFormat: 'glb' as const,
    supportsCancel: true,
    supportsTimeout: true,
    backendId: 'mock-remote',
    kind: 'mock' as const
  }

  async generate(
    spec: CharacterSpec,
    references: VisionImageInput[],
    onProgress: (p: GenerationProgress) => void,
    signal?: GenerationAbortSignal
  ): Promise<GeneratedModelResult> {
    return runBackendGenerate(this.capabilities.backendId, spec, references, onProgress, signal)
  }
}

/**
 * Embedded local AI 3D runtime provider (Phase 1: infrastructure only).
 * Marked kind=real - NEVER a mock. When no runtime is installed/ready the
 * backend returns an explicit unavailable error (no silent mock fallback).
 */
export class EmbeddedAI3DProvider implements AIImage3DProvider {
  readonly id = 'embedded-ai-3d'
  readonly name = 'Embedded AI 3D（本地）'
  readonly description =
    '本地 AI 3D Runtime（多 Runtime 管理）。阶段 1 仅基础设施，未安装 Runtime 时不可用，绝不回退 Mock。'
  readonly requiresBackend = true
  readonly capabilities = {
    mode: 'local' as const,
    gpuRequired: true,
    maxReferences: 4,
    outputFormat: 'glb' as const,
    supportsCancel: true,
    supportsTimeout: true,
    backendId: 'embedded-ai-3d',
    kind: 'real' as const
  }

  async generate(
    spec: CharacterSpec,
    references: VisionImageInput[],
    onProgress: (p: GenerationProgress) => void,
    signal?: GenerationAbortSignal
  ): Promise<GeneratedModelResult> {
    return runBackendGenerate(this.capabilities.backendId, spec, references, onProgress, signal)
  }
}
