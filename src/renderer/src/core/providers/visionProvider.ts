import type { CharacterAsset, CharacterSpec } from '@shared/types'
import type { ReferenceView } from '@shared/types'
import type { ViewAnalysis, ViewConflict } from '@shared/types'

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
 *
 * Phase 2.2 additions (all optional, Phase 2.1 single-image results remain
 * fully compatible): `perView` carries each view's own observation and
 * `conflicts` lists fields where views disagreed. `conflicts` MUST come from
 * the backend CrossViewResolver, never be trusted from the model.
 */
export interface VisionAnalysisResult {
  specPatch: Partial<CharacterSpec>
  /** 0..1 overall confidence of the analysis. */
  confidence: number
  notes: string[]
  warnings: string[]
  sourceImageIds: string[]
  providerId?: string
  perView?: ViewAnalysis[]
  conflicts?: ViewConflict[]
  /** Phase 3-2: observed appearance suggestions (optional, go through review). */
  assetPatch?: Partial<CharacterAsset>
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
