import type { CharacterSpec, ModelFormat } from '@shared/types'
import type { VisionImageInput } from './visionProvider'

/** Cooperative cancellation flag for a running generation job. */
export interface GenerationAbortSignal {
  aborted: boolean
}

/** Capability description so clients can reason about a provider. */
export interface ProviderCapabilities {
  mode: 'local' | 'cloud'
  gpuRequired: boolean
  maxReferences: number
  outputFormat: ModelFormat
  supportsCancel: boolean
  supportsTimeout: boolean
  /** Backend provider id to request when the job runs server-side. */
  backendId: string
}

/**
 * Result of an AI image-to-3D generation run.
 */
export interface GeneratedModelResult {
  modelId: string
  name: string
  format: ModelFormat
  /** Raw GLB bytes produced by the provider. */
  bytes: ArrayBuffer
  /** Optional absolute path when the provider stored the file itself. */
  filePath?: string
  /** Phase 2.3-C output metadata (optional). */
  sizeBytes?: number
  providerId?: string
  sourceJobId?: string
  mime?: string
}

export interface GenerationProgress {
  step: number
  totalSteps: number
  /** 0..1 */
  percent: number
  message: string
}

/**
 * AI Image-to-3D provider contract.
 *
 * Concrete providers are injected at the call site; the app never depends on a
 * specific vendor. A real provider (e.g. Trellis / Meshy) can be swapped in
 * behind this interface without touching the rest of the app.
 */
export interface AIImage3DProvider {
  readonly id: string
  readonly name: string
  readonly description: string
  readonly capabilities: ProviderCapabilities
  /** True when the provider requires the FastAPI backend to be reachable. */
  readonly requiresBackend: boolean
  generate(
    spec: CharacterSpec,
    references: VisionImageInput[],
    onProgress: (p: GenerationProgress) => void,
    signal?: GenerationAbortSignal
  ): Promise<GeneratedModelResult>
}
