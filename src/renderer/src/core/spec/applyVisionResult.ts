import type {
  AnatomyGraph,
  AppearanceProfile,
  BodyType,
  CharacterGender,
  CharacterSpec,
  CharacterStyle,
  CharacterType,
  FurProfile,
  SpeciesInfo,
  SpeciesKind
} from '@shared/types'

/**
 * A user-confirmed patch extracted from a vision analysis. The AI result is
 * only a *source of suggestions*; what lands in the CharacterSpec is exactly
 * the subset the user accepted.
 */
export type ConfirmedSpecPatch = Partial<
  Pick<
    CharacterSpec,
    'name' | 'description' | 'userNotes' | 'characterType' | 'bodyType' | 'style' | 'gender' | 'heightCm' | 'visionAnalysis'
  >
> & {
  species?: Partial<SpeciesInfo>
  anatomy?: Partial<AnatomyGraph>
  fur?: Partial<FurProfile>
  appearance?: Partial<AppearanceProfile>
}

export const CHARACTER_TYPES: readonly CharacterType[] = [
  'human',
  'anime-human',
  'anthro',
  'animal',
  'fantasy-creature',
  'robot',
  'alien',
  'custom'
]

export const CHARACTER_STYLES: readonly CharacterStyle[] = ['stylized', 'realistic', 'anime', 'pixel']

export const CHARACTER_GENDERS: readonly CharacterGender[] = ['female', 'male', 'neutral']

export const BODY_TYPES: readonly BodyType[] = ['humanoid', 'biped-anthro', 'quadruped', 'bird', 'dragon', 'custom']

export const SPECIES_KINDS: readonly SpeciesKind[] = [
  'wolf',
  'fox',
  'cat',
  'dog',
  'bear',
  'rabbit',
  'deer',
  'dragon',
  'bird',
  'reptile',
  'aquatic',
  'insect',
  'custom'
]

const HEIGHT_MIN = 50
const HEIGHT_MAX = 300

function clampEnum<T extends string>(value: unknown, allowed: readonly T[]): T | undefined {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value) ? (value as T) : undefined
}

function clampNumber(value: unknown, min: number, max: number): number | undefined {
  if (typeof value !== 'number' || Number.isNaN(value)) return undefined
  return Math.min(max, Math.max(min, Math.round(value)))
}

function clampConfidence(value: unknown): number | undefined {
  if (typeof value !== 'number' || Number.isNaN(value)) return undefined
  return Math.min(1, Math.max(0, value))
}

function clampHexColors(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined
  const out = value.filter((c) => typeof c === 'string' && /^#[0-9a-fA-F]{6}$/.test(c))
  return out.length > 0 ? out : undefined
}

/**
 * Validates, clamps and merges a confirmed patch against the current spec.
 * Returns a fully-formed Partial<CharacterSpec> safe to pass to updateSpec.
 * Unknown/illegal values are dropped rather than guessed.
 */
export function applyVisionResult(
  current: CharacterSpec,
  patch: ConfirmedSpecPatch
): Partial<CharacterSpec> {
  const out: Partial<CharacterSpec> = {}

  if (typeof patch.name === 'string' && patch.name.trim()) out.name = patch.name.trim()
  if (typeof patch.description === 'string') out.description = patch.description
  if (typeof patch.userNotes === 'string') out.userNotes = patch.userNotes

  const characterType = clampEnum(patch.characterType, CHARACTER_TYPES)
  if (characterType) out.characterType = characterType

  const bodyType = clampEnum(patch.bodyType, BODY_TYPES)
  if (bodyType) out.bodyType = bodyType

  const style = clampEnum(patch.style, CHARACTER_STYLES)
  if (style) out.style = style

  const gender = clampEnum(patch.gender, CHARACTER_GENDERS)
  if (gender) out.gender = gender

  const heightCm = clampNumber(patch.heightCm, HEIGHT_MIN, HEIGHT_MAX)
  if (heightCm !== undefined) out.heightCm = heightCm

  if (patch.species) {
    const primary = clampEnum(patch.species.primary, SPECIES_KINDS)
    const secondary = clampEnum(patch.species.secondary, SPECIES_KINDS)
    const confidence = clampConfidence(patch.species.confidence)
    const next: Partial<SpeciesInfo> = {}
    if (primary) next.primary = primary
    if (patch.species.primary === 'custom' || (primary === undefined && patch.species.primary !== undefined)) {
      next.primary = 'custom'
    }
    if (secondary) next.secondary = secondary
    if (confidence !== undefined) next.confidence = confidence
    if (typeof patch.species.label === 'string') next.label = patch.species.label
    if (Object.keys(next).length > 0) out.species = { ...current.species, ...next }
  }

  if (patch.anatomy) {
    const next: Partial<AnatomyGraph> = {}
    const boolKeys = [
      'hasHead',
      'hasFace',
      'hasTorso',
      'hasLimbs',
      'wings',
      'ears',
      'horns',
      'antlers',
      'snout',
      'muzzle',
      'beak',
      'paws',
      'claws',
      'hooves',
      'fins',
      'tentacles',
      'extraLimbs'
    ] as const
    for (const key of boolKeys) {
      const v = patch.anatomy[key]
      if (typeof v === 'boolean') next[key] = v
    }
    const tail = clampEnum(patch.anatomy.tail, ['none', 'single', 'multiple'] as const)
    if (tail) next.tail = tail
    if (Array.isArray(patch.anatomy.customAppendages)) {
      next.customAppendages = patch.anatomy.customAppendages.filter((s) => typeof s === 'string')
    }
    if (Object.keys(next).length > 0) out.anatomy = { ...current.anatomy, ...next }
  }

  if (patch.fur) {
    const next: Partial<FurProfile> = {}
    if (typeof patch.fur.enabled === 'boolean') next.enabled = patch.fur.enabled
    const furStyle = clampEnum(patch.fur.style, ['none', 'toon', 'anime', 'stylized', 'realistic'] as const)
    if (furStyle) next.style = furStyle
    const furLength = clampEnum(patch.fur.length, ['short', 'medium', 'long'] as const)
    if (furLength) next.length = furLength
    if (Array.isArray(patch.fur.colors)) next.colors = patch.fur.colors.filter((s) => typeof s === 'string')
    if (Array.isArray(patch.fur.patterns)) next.patterns = patch.fur.patterns.filter((s) => typeof s === 'string')
    if (Object.keys(next).length > 0) out.fur = { ...current.fur, ...next }
  }

  if (patch.appearance) {
    const next: Partial<AppearanceProfile> = {}
    if (typeof patch.appearance.baseColor === 'string' && /^#[0-9a-fA-F]{6}$/.test(patch.appearance.baseColor)) {
      next.baseColor = patch.appearance.baseColor
    }
    if (Array.isArray(patch.appearance.secondaryColors)) {
      next.secondaryColors = patch.appearance.secondaryColors.filter((s) => typeof s === 'string')
    }
    if (Array.isArray(patch.appearance.patterns)) {
      next.patterns = patch.appearance.patterns.filter((s) => typeof s === 'string')
    }
    if (Array.isArray(patch.appearance.markings)) {
      next.markings = patch.appearance.markings.filter((s) => typeof s === 'string')
    }
    const palette = clampHexColors(patch.appearance.palette)
    if (palette) next.palette = palette
    if (Object.keys(next).length > 0) out.appearance = { ...current.appearance, ...next }
  }

  if (patch.visionAnalysis) {
    const va = patch.visionAnalysis
    if (typeof va.providerId === 'string' && Array.isArray(va.sourceImageIds)) {
      out.visionAnalysis = {
        providerId: va.providerId,
        analyzedAt: typeof va.analyzedAt === 'string' ? va.analyzedAt : new Date().toISOString(),
        sourceImageIds: va.sourceImageIds.filter((s) => typeof s === 'string'),
        confidence: clampConfidence(va.confidence) ?? 0
      }
    }
  }

  return out
}
