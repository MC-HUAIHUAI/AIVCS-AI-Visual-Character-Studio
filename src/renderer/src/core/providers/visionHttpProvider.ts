import type { AIVisionProvider, VisionAnalysisResult, VisionImageInput } from './visionProvider'
import { AIVCS_BACKEND_URL } from './httpProvider'

interface VisionAnalysisDto {
  specPatch: Record<string, unknown>
  confidence: number
  notes: string[]
  warnings: string[]
  sourceImageIds: string[]
  providerId: string
}

/**
 * Drives vision analysis through the local FastAPI backend
 * (POST /api/v1/vision/analyze). The backend holds its own AIVisionProvider
 * registry; this client only translates HTTP into the frontend AIVisionProvider
 * contract. Phase 2.1 the backend always uses the Mock provider.
 */
export class VisionHttpProvider implements AIVisionProvider {
  readonly id = 'backend-fastapi-vision'
  readonly displayName = 'FastAPI 后端（Kimi/Mock）'
  readonly description =
    '通过本地 FastAPI 后端运行视觉分析；后端已配置 Kimi Key 时使用 Kimi，否则回退 Mock。需要运行 `npm run backend`。'
  readonly requiresBackend = true

  async analyze(
    refs: VisionImageInput[],
    onProgress?: (progress: number) => void
  ): Promise<VisionAnalysisResult> {
    onProgress?.(0.2)
    const res = await fetch(`${AIVCS_BACKEND_URL}/api/v1/vision/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: 'auto',
        references: refs.map((r) => ({
          imageId: r.imageId,
          dataUrl: r.dataUrl,
          view: r.view ?? null
        }))
      })
    })
    if (!res.ok) {
      throw new Error(`视觉分析失败（HTTP ${res.status}）。后端是否已启动？`)
    }
    const dto = (await res.json()) as VisionAnalysisDto
    onProgress?.(1)

    return {
      specPatch: dto.specPatch as VisionAnalysisResult['specPatch'],
      confidence: dto.confidence,
      notes: dto.notes,
      warnings: dto.warnings,
      sourceImageIds: dto.sourceImageIds,
      providerId: dto.providerId
    }
  }
}
