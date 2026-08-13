import type { AIVisionProvider, VisionAnalysisResult, VisionImageInput } from './visionProvider'

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

/**
 * Fully local mock vision provider. It does NOT look at the image content, does
 * not touch the network and does not read any API key. It replays a short
 * analysis with simulated progress and returns a deterministic, honest result
 * flagged as mock so the UI never mistakes it for real analysis.
 */
export class MockVisionProvider implements AIVisionProvider {
  readonly id = 'mock-vision'
  readonly displayName = 'Mock（本地）'
  readonly description = '本地模拟视觉分析，未真正识别图片，无需后端与 API。'
  readonly requiresBackend = false

  async analyze(
    refs: VisionImageInput[],
    onProgress?: (progress: number) => void
  ): Promise<VisionAnalysisResult> {
    onProgress?.(0.15)
    await sleep(260)
    onProgress?.(0.5)
    await sleep(300)
    onProgress?.(0.8)
    await sleep(180)
    onProgress?.(1)

    return {
      specPatch: {
        characterType: 'human'
      },
      confidence: 0.1,
      notes: ['Mock 模式：未真正分析图片'],
      warnings: ['无法确定角色物种，请选择或补充参考图。'],
      sourceImageIds: refs.map((r) => r.imageId),
      providerId: this.id
    }
  }
}
