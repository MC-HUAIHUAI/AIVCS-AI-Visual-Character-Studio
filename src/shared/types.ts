/**
 * AIVCS shared contracts.
 * Used by Electron main, preload and the renderer so the IPC boundary is typed.
 */

export type CharacterStyle = 'stylized' | 'realistic' | 'anime' | 'pixel'

export type CharacterGender = 'female' | 'male' | 'neutral'

export type ModelFormat = 'glb' | 'gltf' | 'vrm' | 'l2d'

export type ModelSource = 'generated' | 'imported' | 'demo'

/* ------------------------------------------------------------------------ */
/* Non-human / creature support (Phase 1)                                    */
/* ------------------------------------------------------------------------ */

export type CharacterType =
  | 'human'
  | 'anime-human'
  | 'anthro'
  | 'animal'
  | 'fantasy-creature'
  | 'robot'
  | 'alien'
  | 'custom'

export type SpeciesKind =
  | 'wolf'
  | 'fox'
  | 'cat'
  | 'dog'
  | 'bear'
  | 'rabbit'
  | 'deer'
  | 'dragon'
  | 'bird'
  | 'reptile'
  | 'aquatic'
  | 'insect'
  | 'custom'

export interface SpeciesInfo {
  primary: SpeciesKind
  /** Secondary/mixed species, null when absent. */
  secondary: SpeciesKind | null
  /** 0..1 AI confidence. null means "not determined yet". */
  confidence: number | null
  /** Free-text species label for custom species. */
  label: string | null
}

export type BodyType = 'humanoid' | 'biped-anthro' | 'quadruped' | 'bird' | 'dragon' | 'custom'

export type FurStyle = 'none' | 'toon' | 'anime' | 'stylized' | 'realistic'

export type FurLength = 'short' | 'medium' | 'long'

export interface FurProfile {
  enabled: boolean
  style: FurStyle
  length: FurLength
  colors: string[]
  patterns: string[]
}

export interface AppearanceProfile {
  baseColor: string | null
  secondaryColors: string[]
  patterns: string[]
  markings: string[]
  /** Extracted color palette in #RRGGBB format (Phase 2.1 vision output). */
  palette?: string[]
}

/* ------------------------------------------------------------------------ */
/* CharacterAsset - derived renderable appearance (Phase 3-1)                */
/* ------------------------------------------------------------------------ */

/** Provenance of a CharacterAsset field. */
export type AssetSource = 'observed' | 'derived' | 'none'

/**
 * Derived, renderable structured appearance - an intermediate layer between
 * the CharacterSpec (the single semantic source, unchanged) and any 3D/2D
 * output. Values are either derived deterministically from the CharacterSpec
 * (source 'derived'), written from a user-confirmed vision assetPatch (source
 * 'observed'), or absent (source 'none'). This is NOT a replacement for the
 * CharacterSpec and is not wired to real 3D/2D output yet.
 */
export interface CharacterAsset {
  version: 1
  palette: string[]
  baseColor: string | null
  secondaryColors: string[]
  furColors: string[]
  furPatterns: string[]
  hairColor: string | null
  eyeColor: string | null
  skinColor: string | null
  outfitColors: string[]
  backPattern: string | null
  /** Per-field provenance keyed by CharacterAsset field name. */
  source: Record<string, AssetSource>
}

/** Vision-observed appearance patch (Phase 3-2). All fields optional. */
export interface AssetPatch {
  hairColor?: string | null
  eyeColor?: string | null
  skinColor?: string | null
  outfitColors?: string[]
  backPattern?: string | null
}

/* ------------------------------------------------------------------------ */
/* 2D layered portrait (Phase 3-4)                                           */
/* ------------------------------------------------------------------------ */

export type Portrait2DLayerId =
  | 'body'
  | 'outfit'
  | 'face'
  | 'eyes'
  | 'hair'
  | 'accessory'

export interface Portrait2DLayer {
  id: Portrait2DLayerId
  /** z-order; higher draws on top. Fixed per layer. */
  order: number
  /** Deterministic SVG fragment for this layer. */
  svg: string
  /** CharacterAsset field(s) that drove this layer (provenance preserved). */
  sources: Record<string, AssetSource>
  /** Phase 3-4.5: deterministic animation anchor (metadata only, never affects SVG). */
  anchor?: Portrait2DAnchor
}

export interface Portrait2DAnchor {
  /** x in portrait coordinate space (origin top-left). */
  x: number
  /** y in portrait coordinate space (origin top-left). */
  y: number
}

/** Animation parameter declaration (declared, never evaluated this stage). */
export type Portrait2DParameterId = 'headYaw' | 'headPitch' | 'eyeOpen' | 'mouthOpen' | 'bodySway'

export interface Portrait2DParameterSpec {
  id: Portrait2DParameterId
  /** Normalized range, e.g. [-1, 1]. */
  range: [number, number]
  /** Rest value, e.g. 0. */
  default: number
  /** Layers this parameter would drive (metadata binding). */
  binds: Portrait2DLayerId[]
}

/** Individually animatable appendage (declared only when anatomy says so). */
export interface AppendageSpec {
  id: string
  /** Anchor for this appendage (metadata only). */
  anchor: Portrait2DAnchor
  /** Layer the appendage lives in (always 'accessory'). */
  layer: Portrait2DLayerId
}

export interface Portrait2DDescriptor {
  version: 1
  kind: '2d-layered'
  note: '2D layered / Live2D-ready，非 Cubism Runtime，不含 physics/parameter/motion'
  width: number
  height: number
  layers: Portrait2DLayer[] // in draw order
  frontView: boolean
  /** Metadata only - never fabricated as a texture this stage. */
  backPattern: string | null
  /** Render-parameter source snapshot. */
  assetSource: CharacterAsset
  /** Reserved extension point for a future Cubism exporter. */
  cubism: { present: false; parameters: Record<Portrait2DParameterId, string> }
  /** Phase 3-4.5: declared animation parameters (metadata only, not evaluated). */
  parameters?: Portrait2DParameterSpec[]
  /** Phase 3-4.5: individually animatable appendages (only when anatomy says so). */
  appendages?: AppendageSpec[]
}

export interface Portrait2DResult {
  /** Byte-deterministic SVG document. */
  svg: string
  descriptor: Portrait2DDescriptor
  fileName: string
  mime: 'image/svg+xml'
}

export interface Portrait2DUnsupported {
  status: 'unsupported'
  bodyType: string
  reason: string
}

export type Portrait2DOutput =
  | { status: 'ok'; result: Portrait2DResult }
  | Portrait2DUnsupported

export type TailMode = 'none' | 'single' | 'multiple'

/**
 * Generic anatomy graph. Every part is optional and independent; the system
 * never assumes a humanoid skeleton. Appendages beyond the fixed set live in
 * `customAppendages`.
 */
export interface AnatomyGraph {
  hasHead: boolean
  hasFace: boolean
  hasTorso: boolean
  hasLimbs: boolean
  tail: TailMode
  wings: boolean
  ears: boolean
  horns: boolean
  antlers: boolean
  snout: boolean
  muzzle: boolean
  beak: boolean
  paws: boolean
  claws: boolean
  hooves: boolean
  fins: boolean
  tentacles: boolean
  extraLimbs: boolean
  customAppendages: string[]
}

/**
 * Character Specification - the canonical data structure describing a virtual
 * character. It is the contract exchanged between the app, the AI providers and
 * the exporters.
 */
export interface CharacterSpec {
  id: string
  name: string
  style: CharacterStyle
  gender: CharacterGender
  heightCm: number
  description: string
  referenceImageIds: string[]
  tags: string[]
  createdAt: string
  updatedAt: string

  /** New in Phase 1 - non-human support. All fields have sane defaults. */
  characterType: CharacterType
  species: SpeciesInfo
  bodyType: BodyType
  anatomy: AnatomyGraph
  fur: FurProfile
  appearance: AppearanceProfile

  /** New in Phase 2.1 - vision analysis provenance (written on user acceptance). */
  visionAnalysis?: VisionAnalysisMeta
  userNotes?: string
}

/* ------------------------------------------------------------------------ */
/* Rigging                                                                   */
/* ------------------------------------------------------------------------ */

export type RigProfileId = 'humanoid' | 'quadruped' | 'anthropomorphic' | 'bird' | 'dragon' | 'custom'

export interface RigBone {
  id: string
  label: string
  parent?: string
}

export interface RigProfile {
  id: RigProfileId
  label: string
  bones: RigBone[]
}

/**
 * Skeletal templates per rig profile. A real pipeline would merge these with
 * the AnatomyGraph to build the final Character Rig Graph. Non-human parts
 * (tail/ear/horn/wing/...) become extra bones that VRM keeps separately.
 */
export const RIG_PROFILES: RigProfile[] = [
  {
    id: 'humanoid',
    label: '人类',
    bones: [
      { id: 'hips', label: '骨盆' },
      { id: 'spine', label: '脊椎', parent: 'hips' },
      { id: 'chest', label: '胸腔', parent: 'spine' },
      { id: 'neck', label: '颈部', parent: 'chest' },
      { id: 'head', label: '头部', parent: 'neck' },
      { id: 'leftArm', label: '左臂', parent: 'chest' },
      { id: 'leftHand', label: '左手', parent: 'leftArm' },
      { id: 'rightArm', label: '右臂', parent: 'chest' },
      { id: 'rightHand', label: '右手', parent: 'rightArm' },
      { id: 'leftLeg', label: '左腿', parent: 'hips' },
      { id: 'leftFoot', label: '左脚', parent: 'leftLeg' },
      { id: 'rightLeg', label: '右腿', parent: 'hips' },
      { id: 'rightFoot', label: '右脚', parent: 'rightLeg' }
    ]
  },
  {
    id: 'quadruped',
    label: '四足动物',
    bones: [
      { id: 'hips', label: '骨盆' },
      { id: 'spine', label: '脊椎', parent: 'hips' },
      { id: 'chest', label: '胸腔', parent: 'spine' },
      { id: 'neck', label: '颈部', parent: 'chest' },
      { id: 'head', label: '头部', parent: 'neck' },
      { id: 'frontLeg_L', label: '前腿（左）', parent: 'chest' },
      { id: 'frontLeg_R', label: '前腿（右）', parent: 'chest' },
      { id: 'rearLeg_L', label: '后腿（左）', parent: 'hips' },
      { id: 'rearLeg_R', label: '后腿（右）', parent: 'hips' },
      { id: 'tail', label: '尾巴', parent: 'hips' }
    ]
  },
  {
    id: 'anthropomorphic',
    label: '兽人（直立）',
    bones: [
      { id: 'hips', label: '骨盆' },
      { id: 'spine', label: '脊椎', parent: 'hips' },
      { id: 'chest', label: '胸腔', parent: 'spine' },
      { id: 'neck', label: '颈部', parent: 'chest' },
      { id: 'head', label: '头部', parent: 'neck' },
      { id: 'leftArm', label: '左臂', parent: 'chest' },
      { id: 'rightArm', label: '右臂', parent: 'chest' },
      { id: 'leftLeg', label: '左腿', parent: 'hips' },
      { id: 'rightLeg', label: '右腿', parent: 'hips' },
      { id: 'tail', label: '尾巴', parent: 'hips' },
      { id: 'ears_L', label: '左耳', parent: 'head' },
      { id: 'ears_R', label: '右耳', parent: 'head' }
    ]
  },
  {
    id: 'bird',
    label: '鸟类',
    bones: [
      { id: 'hips', label: '骨盆' },
      { id: 'spine', label: '脊椎', parent: 'hips' },
      { id: 'neck', label: '颈部', parent: 'spine' },
      { id: 'head', label: '头部', parent: 'neck' },
      { id: 'wing_L', label: '左翅', parent: 'spine' },
      { id: 'wing_R', label: '右翅', parent: 'spine' },
      { id: 'leg_L', label: '左腿', parent: 'hips' },
      { id: 'leg_R', label: '右腿', parent: 'hips' },
      { id: 'tail', label: '尾羽', parent: 'hips' }
    ]
  },
  {
    id: 'dragon',
    label: '龙',
    bones: [
      { id: 'hips', label: '骨盆' },
      { id: 'spine', label: '脊椎', parent: 'hips' },
      { id: 'chest', label: '胸腔', parent: 'spine' },
      { id: 'neck', label: '颈部', parent: 'chest' },
      { id: 'head', label: '头部', parent: 'neck' },
      { id: 'arm_L', label: '左臂', parent: 'chest' },
      { id: 'arm_R', label: '右臂', parent: 'chest' },
      { id: 'leg_L', label: '左腿', parent: 'hips' },
      { id: 'leg_R', label: '右腿', parent: 'hips' },
      { id: 'wing_L', label: '左翼', parent: 'chest' },
      { id: 'wing_R', label: '右翼', parent: 'chest' },
      { id: 'tail', label: '尾巴', parent: 'hips' },
      { id: 'horn_L', label: '左角', parent: 'head' },
      { id: 'horn_R', label: '右角', parent: 'head' }
    ]
  },
  {
    id: 'custom',
    label: '自定义',
    bones: []
  }
]

export function getRigProfile(id: RigProfileId): RigProfile {
  return RIG_PROFILES.find((p) => p.id === id) ?? RIG_PROFILES[0]
}

/* ------------------------------------------------------------------------ */
/* Natural language editing                                                  */
/* ------------------------------------------------------------------------ */

/**
 * Structured command produced when a natural-language edit request is
 * interpreted (e.g. "把尾巴变得更蓬松" -> modify_appendage/tail/fluffiness).
 */
export interface CharacterEditCommand {
  id: string
  operation: string
  target: string
  parameters: Record<string, string>
  rawInput: string
  createdAt: string
}

/* ------------------------------------------------------------------------ */
/* Vision analysis (Phase 2.1)                                               */
/* ------------------------------------------------------------------------ */

/** Camera/pose view of a reference image. */
export type ReferenceView = 'front' | 'side' | 'back' | 'custom'

/**
 * How multiple reference images are analyzed. Phase 2.2 only implements
 * 'joint' (one request with all views); 'per-view' is reserved for the future.
 */
export type AnalysisMode = 'joint' | 'per-view'

/** Per-view provenance metadata stored on an accepted CharacterSpec. */
export interface VisionPerViewMeta {
  view: ReferenceView
  sourceImageId: string
  confidence: number
}

/**
 * Provenance metadata attached to a CharacterSpec once a vision analysis
 * suggestion has been accepted by the user.
 */
export interface VisionAnalysisMeta {
  providerId: string
  analyzedAt: string
  sourceImageIds: string[]
  confidence: number
  /** Optional per-view metadata (Phase 2.2, accepted spec only). */
  perView?: VisionPerViewMeta[]
  resolvedAt?: string
}

/* ------------------------------------------------------------------------ */
/* Multi-view analysis (Phase 2.2)                                           */
/* ------------------------------------------------------------------------ */

/**
 * A single view's observation produced by a vision provider. It is an
 * observation only - the final unified result and conflict detection are owned
 * by the CrossViewResolver, never by the provider.
 */
export interface ViewAnalysis {
  view: ReferenceView
  sourceImageId: string
  specPatch: Partial<CharacterSpec>
  /** Overall confidence of this view's analysis (0..1). */
  confidence: number
  notes: string[]
  warnings: string[]
}

export interface ViewConflictCandidate {
  value: unknown
  view: ReferenceView | null
  confidence: number
}

/**
 * A field where two or more views disagreed. `resolvedTo` holds the
 * deterministic default (highest-confidence candidate) and is meant for
 * runtime/UI; unresolved conflicts are never persisted into CharacterSpec.
 */
export interface ViewConflict {
  field: string
  fieldLabel: string
  candidates: ViewConflictCandidate[]
  resolvedTo: ViewConflictCandidate | null
}

export interface ImageAsset {
  id: string
  name: string
  mime: string
  width: number
  height: number
  dataUrl: string
  bytes: number
  addedAt: string
  /** Optional reference view tag for multi-view analysis (Phase 2.1+). */
  view?: ReferenceView | null
}

export interface ModelAsset {
  id: string
  name: string
  source: ModelSource
  format: ModelFormat
  /** Absolute path on disk when available, otherwise null for demo/builtin. */
  filePath: string | null
  addedAt: string
  /** Phase 2.3-C output metadata (optional, from the job result - never guessed). */
  providerId?: string
  sourceJobId?: string
  sizeBytes?: number
  mime?: string
  /** Phase 2.5-B: analyzer statistics (optional, from the backend - never guessed). */
  glbStats?: GlbStats
  /** Phase 2.5-C: future normalization notes (optional; empty = never shown). */
  normalizations?: string[]
}

/* ------------------------------------------------------------------------ */
/* GLB asset analysis (Phase 2.5)                                            */
/* ------------------------------------------------------------------------ */

export interface GlbBounds {
  min: [number, number, number]
  max: [number, number, number]
}

export interface GlbDimensions {
  x: number
  y: number
  z: number
}

export interface GlbCenter {
  x: number
  y: number
  z: number
}

export interface MeshStat {
  name: string
  index: number
  vertexCount: number
  indexCount: number
  triangleCount: number
  materialIndex: number | null
  hasNormals: boolean
  hasUVs: boolean
  mode: number
}

/** Structural statistics produced by the GLB Asset Analyzer. */
export interface GlbStats {
  format: string
  version: number
  sizeBytes: number
  meshCount: number
  primitiveCount: number
  vertexCount: number
  indexCount: number
  triangleCount: number
  materialCount: number
  textureCount: number
  hasNormals: boolean
  hasUVs: boolean
  bounds: GlbBounds | null
  dimensions: GlbDimensions | null
  center: GlbCenter | null
  meshStats: MeshStat[]
  warnings: string[]
  /** Phase 2.7-D: whether the GLB carries a `skins` entry (skinned mesh). Optional. */
  skinned?: boolean
}

export interface ProjectData {
  version: 1
  name: string
  createdAt: string
  updatedAt: string
  spec: CharacterSpec
  images: ImageAsset[]
  models: ModelAsset[]
  /** Phase 3-1: derived renderable appearance (optional, backward compatible). */
  characterAsset?: CharacterAsset
}

export interface ProjectSaveResult {
  ok: boolean
  path?: string
  error?: string
}

export interface ProjectLoadResult {
  ok: boolean
  project?: ProjectData
  path?: string
  error?: string
}

export interface ImportImageResult {
  ok: boolean
  assets?: ImageAsset[]
  error?: string
}

export interface ExportModelResult {
  ok: boolean
  path?: string
  error?: string
}

/** Generated / AI pipeline job steps pushed to the renderer. */
export interface GenerationJobStep {
  index: number
  label: string
  status: 'pending' | 'running' | 'done' | 'failed'
}

export interface GenerationJob {
  id: string
  provider: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'timed_out' | 'cancelled'
  progress: number
  message: string
  steps: GenerationJobStep[]
  createdAt: string
  finishedAt: string | null
  error: string | null
  resultModelId: string | null
  /** Phase 2.3 state machine metadata (optional, backward compatible). */
  deadlineAt?: number | null
  durationMs?: number | null
  retryable?: boolean
  cancelledByUser?: boolean
  timedOut?: boolean
  attempt?: number
}

/**
 * Reserved contract for a future third-party image-to-3D provider
 * (Phase 2.4-D-pre). NOT wired to any network/API in this release: even when
 * `enabled` is true, nothing sends a request, calls a provider, or validates
 * the address. `enabled` only marks the future config contract.
 *
 * API keys are intentionally NOT part of this type and must never enter
 * ProjectData / CharacterSpec / ModelAsset - real credentials get secure
 * storage only when the provider is actually implemented.
 */
export interface External3DProviderSettings {
  /** Default false. Reserved flag for a future external provider. */
  enabled: boolean
  /** Vendor-agnostic provider id, e.g. "external-3d". */
  providerId: string
  /** Empty by default; never contacted while disabled. String/format check only. */
  baseUrl: string
}

export const IPC_CHANNELS = {
  saveProject: 'project:save',
  loadProject: 'project:load',
  importImages: 'project:import-images',
  exportModel: 'model:export',
  pickExportPath: 'model:pick-export-path'
} as const
