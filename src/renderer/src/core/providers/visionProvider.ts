import type { CharacterSpec } from '@shared/types'
import type { ReferenceView } from '@shared/types'

export type { ReferenceView } from '@shared/types'

/**
 * One reference image handed to a vision provider. The provider never needs
 * access to the file system - the image is already in memory as a data URL.
 */
export interface VisionImageInput {
  imageId: string
  dataUrl: string
  view?: ReferenceView | null
}

/**
 * Result of a vision analysis run. `specPatch` holds the AI *suggestions* only;
 * it must never be written to the CharacterSpec directly - the user reviews and
 * confirms each suggestion first.
 */
export interface VisionAnalysisResult {
  specPatch: Partial<CharacterSpec>
  /** 0..1 overall confidence of the analysis. */
  confidence: number
  notes: string[]
  warnings: string[]
  sourceImageIds: string[]
  providerId?: string
}

/**
 * AI vision analysis provider contract (image reference -> CharacterSpec patch
 * suggestions). Mirrors the existing AIImage3DProvider style: id / displayName /
 * requiresBackend + an analyze method with progress.
 */
export interface AIVisionProvider {
  readonly id: string
  readonly displayName: string
  readonly description: string
  readonly requiresBackend: boolean
  analyze(
    refs: VisionImageInput[],
    onProgress?: (progress: number) => void
  ): Promise<VisionAnalysisResult>
}
