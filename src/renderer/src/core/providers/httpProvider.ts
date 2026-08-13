import type { AIImage3DProvider, GeneratedModelResult, GenerationProgress } from './aiProvider'
import type { CharacterSpec, ImageAsset } from '@shared/types'

export const AIVCS_BACKEND_URL = 'http://127.0.0.1:8321'

export async function backendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/health`, { signal: AbortSignal.timeout(2500) })
    return res.ok
  } catch {
    return false
  }
}

interface JobDto {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  progress: number
  message: string
  steps: { index: number; label: string; status: string }[]
  error: string | null
  result: { model_id: string } | null
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

/**
 * Provider that drives the image-to-3D pipeline through the local FastAPI
 * backend. The backend holds its own provider abstraction (Mock + future real
 * providers); this client only translates HTTP into the same AIImage3DProvider
 * contract used by the local mock.
 */
export class BackendImage3DProvider implements AIImage3DProvider {
  readonly id = 'backend-fastapi'
  readonly name = 'FastAPI 后端（Mock）'
  readonly description = '通过本地 FastAPI 后端运行生成流程（使用其 Mock 提供方）。需要运行 `npm run backend`。'
  readonly requiresBackend = true

  async generate(
    spec: CharacterSpec,
    references: ImageAsset[],
    onProgress: (p: GenerationProgress) => void
  ): Promise<GeneratedModelResult> {
    const createRes = await fetch(`${AIVCS_BACKEND_URL}/api/v1/generate/image-to-3d`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: 'mock',
        spec,
        reference_image_ids: references.map((r) => r.id)
      })
    })
    if (!createRes.ok) {
      throw new Error(`Backend rejected generation (HTTP ${createRes.status}). Is the backend running?`)
    }
    const { job_id } = (await createRes.json()) as { job_id: string }

    let job: JobDto
    for (;;) {
      const pollRes = await fetch(`${AIVCS_BACKEND_URL}/api/v1/generate/jobs/${job_id}`)
      if (!pollRes.ok) throw new Error(`Failed to poll job (HTTP ${pollRes.status})`)
      job = (await pollRes.json()) as JobDto

      onProgress({
        step: job.steps.filter((s) => s.status === 'done' || s.status === 'running').length,
        totalSteps: job.steps.length,
        percent: job.progress,
        message: job.message
      })

      if (job.status === 'done') break
      if (job.status === 'failed') throw new Error(job.error ?? 'Generation failed')
      await sleep(450)
    }

    if (!job.result?.model_id) throw new Error('Backend finished without a model id')

    const glbRes = await fetch(`${AIVCS_BACKEND_URL}/api/v1/models/${job.result.model_id}`, {
      signal: AbortSignal.timeout(15000)
    })
    if (!glbRes.ok) throw new Error(`Failed to download model (HTTP ${glbRes.status})`)
    const bytes = await glbRes.arrayBuffer()

    return {
      modelId: job.result.model_id,
      name: 'generated_character',
      format: 'glb',
      bytes
    }
  }
}
