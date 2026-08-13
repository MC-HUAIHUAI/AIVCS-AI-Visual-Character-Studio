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
}

export interface ProjectData {
  version: 1
  name: string
  createdAt: string
  updatedAt: string
  spec: CharacterSpec
  images: ImageAsset[]
  models: ModelAsset[]
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
  status: 'queued' | 'running' | 'done' | 'failed'
  progress: number
  message: string
  steps: GenerationJobStep[]
  createdAt: string
  finishedAt: string | null
  error: string | null
  resultModelId: string | null
}

export const IPC_CHANNELS = {
  saveProject: 'project:save',
  loadProject: 'project:load',
  importImages: 'project:import-images',
  exportModel: 'model:export',
  pickExportPath: 'model:pick-export-path'
} as const
