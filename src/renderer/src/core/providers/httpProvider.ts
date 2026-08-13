import type { AIImage3DProvider, GeneratedModelResult, GenerationProgress } from './aiProvider'
import type { GenerationAbortSignal } from './aiProvider'
import type { CharacterSpec, ModelFormat } from '@shared/types'
import type { VisionImageInput } from './visionProvider'
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

export interface CreateGenerationRequest {
  spec: CharacterSpec
  references: GenerationRequest['references']
  timeoutSeconds?: number
}

export async function createGenerationJob(req: CreateGenerationRequest): Promise<{ jobId: string }> {
  const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/generate/image-to-3d`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider: 'mock',
      spec: req.spec,
      references: req.references,
      timeoutSeconds: req.timeoutSeconds ?? DEFAULT_GENERATION_TIMEOUT_SECONDS
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

  async generate(
    spec: CharacterSpec,
    references: VisionImageInput[],
    onProgress: (p: GenerationProgress) => void,
    signal?: GenerationAbortSignal
  ): Promise<GeneratedModelResult> {
    const created = await createGenerationJob({
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
        bytes
      }
    }
    if (dto?.status === 'cancelled' || signal?.aborted) {
      throw new Error('generation aborted')
    }
    throw new Error(safeErrorMessage(new Error(dto?.error ?? '生成失败')))
  }
}
