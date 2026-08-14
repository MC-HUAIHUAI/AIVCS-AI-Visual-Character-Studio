import type { CharacterAsset, CharacterSpec } from '@shared/types'

/**
 * Phase 3-1: CharacterAsset derivation + merge logic.
 *
 * PURE logic only - no React/Zustand/network. The CharacterSpec remains the
 * single semantic source; CharacterAsset is a derived, renderable appearance
 * layer with explicit per-field provenance:
 *   - 'derived'  = deterministically derived from the CharacterSpec;
 *   - 'observed' = written from a user-confirmed vision assetPatch;
 *   - 'none'     = absent / unknown.
 *
 * Fields that cannot be reliably derived from existing data stay absent
 * (null/[] with source 'none') - nothing is invented.
 */

const HEX = /^#[0-9a-fA-F]{6}$/

const ASSET_FIELDS: (keyof Omit<CharacterAsset, 'version' | 'source'>)[] = [
  'palette',
  'baseColor',
  'secondaryColors',
  'furColors',
  'furPatterns',
  'hairColor',
  'eyeColor',
  'skinColor',
  'outfitColors',
  'backPattern'
]

export function emptyCharacterAsset(): CharacterAsset {
  return {
    version: 1,
    palette: [],
    baseColor: null,
    secondaryColors: [],
    furColors: [],
    furPatterns: [],
    hairColor: null,
    eyeColor: null,
    skinColor: null,
    outfitColors: [],
    backPattern: null,
    source: {}
  }
}

function hexList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined
  const out = value.filter((c) => typeof c === 'string' && HEX.test(c))
  return out
}

function hexOrNull(value: unknown): string | undefined {
  if (typeof value === 'string' && HEX.test(value)) return value
  return undefined
}

function strOrNull(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
}

/**
 * Deterministically derive a CharacterAsset from a CharacterSpec.
 * Only fields with a reliable source in the existing spec are filled with
 * source 'derived'; everything else stays absent (source 'none').
 */
export function deriveCharacterAsset(spec: CharacterSpec): CharacterAsset {
  const asset = emptyCharacterAsset()
  const app = spec.appearance ?? {}
  const fur = spec.fur ?? {}

  if (Array.isArray(app.palette) && app.palette.length > 0) {
    asset.palette = app.palette.filter((c) => HEX.test(c))
  }
  const base = hexOrNull(app.baseColor)
  if (base) {
    asset.baseColor = base
    asset.source.baseColor = 'derived'
  }
  const secondary = hexList(app.secondaryColors)
  if (secondary) {
    asset.secondaryColors = secondary
    asset.source.secondaryColors = 'derived'
  }
  const furColors = hexList(fur.colors)
  if (furColors) {
    asset.furColors = furColors
    asset.source.furColors = 'derived'
  }
  if (Array.isArray(fur.patterns) && fur.patterns.length > 0) {
    asset.furPatterns = fur.patterns.slice(0, 8)
    asset.source.furPatterns = 'derived'
  }
  if (asset.palette.length > 0) {
    asset.source.palette = 'derived'
    // outfitColors are a derived renderable view of the palette.
    asset.outfitColors = asset.palette.slice(0, 4)
    asset.source.outfitColors = 'derived'
  }

  return asset
}

/** True when an assetPatch carries at least one confirmable value. */
export function hasObservableAssetPatch(patch: Partial<CharacterAsset> | null | undefined): boolean {
  if (!patch) return false
  return ASSET_FIELDS.some((f) => {
    const v = patch[f]
    if (Array.isArray(v)) return v.length > 0
    return v !== undefined && v !== null
  })
}

/**
 * Merge a user-confirmed assetPatch into the current CharacterAsset.
 * Every field present in the patch is marked source 'observed'; absent fields
 * keep their existing value/provenance. Values are clamped (hex colors, etc.).
 */
export function applyAssetPatch(
  current: CharacterAsset,
  patch: Partial<CharacterAsset>
): CharacterAsset {
  const next: CharacterAsset = { ...current, source: { ...current.source } }

  const palette = hexList(patch.palette)
  if (palette) {
    next.palette = palette
    next.source.palette = 'observed'
  }
  const base = hexOrNull(patch.baseColor)
  if (base) {
    next.baseColor = base
    next.source.baseColor = 'observed'
  }
  const secondary = hexList(patch.secondaryColors)
  if (secondary) {
    next.secondaryColors = secondary
    next.source.secondaryColors = 'observed'
  }
  const furColors = hexList(patch.furColors)
  if (furColors) {
    next.furColors = furColors
    next.source.furColors = 'observed'
  }
  if (Array.isArray(patch.furPatterns)) {
    next.furPatterns = patch.furPatterns.slice(0, 8)
    next.source.furPatterns = 'observed'
  }
  const hair = hexOrNull(patch.hairColor)
  if (hair) {
    next.hairColor = hair
    next.source.hairColor = 'observed'
  }
  const eye = hexOrNull(patch.eyeColor)
  if (eye) {
    next.eyeColor = eye
    next.source.eyeColor = 'observed'
  }
  const skin = hexOrNull(patch.skinColor)
  if (skin) {
    next.skinColor = skin
    next.source.skinColor = 'observed'
  }
  const outfit = hexList(patch.outfitColors)
  if (outfit) {
    next.outfitColors = outfit
    next.source.outfitColors = 'observed'
  }
  const back = strOrNull(patch.backPattern)
  if (back) {
    next.backPattern = back
    next.source.backPattern = 'observed'
  }

  return next
}
