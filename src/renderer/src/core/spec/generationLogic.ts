import type { CharacterAsset, CharacterSpec, GenerationJob, GenerationJobStep, GlbStats, ImageAsset, ModelAsset, ModelFormat, ModelTextureMeta } from '@shared/types'
import type { VisionImageInput } from '../providers/visionProvider'

/**
 * Pure image-to-3d generation logic (no React/Zustand/network). Drives the job
 * state machine, retry composition and ModelAsset metadata mapping so it can be
 * unit-tested deterministically.
 *
 * States: queued / running / done / failed / timed_out / cancelled.
 * Only queued and running continue polling; all four terminal states stop it.
 */

export type GenerationStatus = GenerationJob['status']

export function isTerminal(status: GenerationStatus): boolean {
  return status === 'done' || status === 'failed' || status === 'timed_out' || status === 'cancelled'
}

export function shouldPoll(status: GenerationStatus): boolean {
  return status === 'queued' || status === 'running'
}

export function canRetry(status: GenerationStatus): boolean {
  return status === 'failed' || status === 'timed_out'
}

export function canCancel(status: GenerationStatus): boolean {
  return status === 'queued' || status === 'running'
}

export interface GenerationRequest {
  spec: CharacterSpec
  references: VisionImageInput[]
  timeoutSeconds?: number
  /** Phase 3-3: optional render-layer (derived CharacterAsset). */
  characterAsset?: CharacterAsset
}

export function referencesWithinLimit(refs: unknown[]): boolean {
  return refs.length <= 4
}

export function buildGenerationRequest(
  spec: CharacterSpec,
  references: ImageAsset[],
  timeoutSeconds?: number,
  characterAsset?: CharacterAsset
): GenerationRequest {
  return {
    spec,
    references: references.map((r) => ({
      imageId: r.id,
      dataUrl: r.dataUrl,
      view: r.view ?? null
    })),
    timeoutSeconds,
    characterAsset
  }
}

export function createQueuedJob(
  id: string,
  providerName: string,
  attempt = 1,
  now = new Date().toISOString()
): GenerationJob {
  return {
    id,
    provider: providerName,
    status: 'queued',
    progress: 0,
    message: '排队中',
    steps: [],
    createdAt: now,
    finishedAt: null,
    error: null,
    resultModelId: null,
    deadlineAt: null,
    durationMs: null,
    retryable: false,
    cancelledByUser: false,
    timedOut: false,
    attempt
  }
}

/** A retry is a BRAND NEW job with a new id; the old job stays for history. */
export function retryJobFrom(
  prev: GenerationJob,
  newId: string,
  now = new Date().toISOString()
): GenerationJob {
  return createQueuedJob(newId, prev.provider, (prev.attempt ?? 1) + 1, now)
}

export interface JobResultDto {
  model_id: string
  format?: string
  mime?: string
  size_bytes?: number
  provider_id?: string
  source_job_id?: string
  stats?: GlbStats
  /** Phase 3-J: texture/paint output metadata (absent/null = shape-only). */
  texture?: ModelTextureMeta | null
}

export interface JobDto {
  job_id: string
  status: GenerationStatus
  progress: number
  message: string
  steps: { index: number; label: string; status: GenerationJobStep['status'] }[]
  error: string | null
  result: JobResultDto | null
  deadline_at?: number | null
  duration_ms?: number | null
  retryable?: boolean
  cancelled_by_user?: boolean
  timed_out?: boolean
  attempt?: number
}

/** Maps a backend poll response onto the local GenerationJob. */
export function applyDtoToJob(base: GenerationJob, dto: JobDto): GenerationJob {
  return {
    ...base,
    status: dto.status,
    progress: Math.round(dto.progress * 100),
    message: dto.message,
    steps: (dto.steps ?? []).map((s, index) => ({
      index: s.index ?? index,
      label: s.label,
      status: s.status
    })),
    error: dto.error ?? null,
    resultModelId: dto.result?.model_id ?? null,
    deadlineAt: dto.deadline_at ?? null,
    durationMs: dto.duration_ms ?? null,
    retryable: dto.retryable ?? false,
    cancelledByUser: dto.cancelled_by_user ?? false,
    timedOut: dto.timed_out ?? false,
    attempt: dto.attempt ?? base.attempt ?? 1
  }
}

export interface ModelAssetMeta {
  providerId?: string
  sourceJobId?: string
  sizeBytes?: number
  format?: ModelFormat
  mime?: string
  filePath?: string | null
  glbStats?: GlbStats
  texture?: ModelTextureMeta | null
  sourceModelId?: string
}

/** Maps generation result metadata to ModelAsset fields (no guessing). */
export function modelAssetFromResult(
  id: string,
  name: string,
  meta: ModelAssetMeta
): ModelAsset {
  return {
    id,
    name,
    source: 'generated',
    format: meta.format ?? 'glb',
    filePath: meta.filePath ?? null,
    addedAt: new Date().toISOString(),
    providerId: meta.providerId,
    sourceJobId: meta.sourceJobId,
    sizeBytes: meta.sizeBytes,
    mime: meta.mime,
    glbStats: meta.glbStats,
    texture: meta.texture,
    sourceModelId: meta.sourceModelId
  }
}

export function safeErrorMessage(err: unknown): string {
  if (err instanceof Error) {
    const msg = err.message
    if (msg && msg.length < 300) return msg
  }
  return '生成失败，请稍后重试'
}

const STATUS_TEXT: Record<GenerationStatus, string> = {
  queued: '排队中',
  running: '生成中',
  done: '完成',
  failed: '失败',
  timed_out: '生成超时',
  cancelled: '已取消'
}

export function statusText(status: GenerationStatus): string {
  return STATUS_TEXT[status] ?? status
}
