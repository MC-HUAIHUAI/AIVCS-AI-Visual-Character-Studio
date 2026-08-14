import type {
  AnatomyGraph,
  AssetSource,
  CharacterAsset,
  CharacterSpec,
  Portrait2DLayer,
  Portrait2DLayerId,
  Portrait2DOutput,
  Portrait2DResult
} from '@shared/types'

/**
 * Phase 3-4: 2D layered portrait generation.
 *
 * PURE logic only - no React/Canvas/network. Deterministically builds a layered
 * front-view SVG portrait from a CharacterSpec + CharacterAsset:
 *
 *   - CharacterSpec is the single semantic source;
 *   - CharacterAsset is the single render-parameter layer (provenance kept);
 *   - humanoid / biped-anthro -> full front 2D layered asset;
 *   - biped-anthro keeps reliable anatomy appendages (ears/horns/tail/wings) as
 *     an accessory layer, only when anatomy says so (never guessed);
 *   - custom -> anatomy-driven partial; only what is reliably expressible;
 *   - quadruped / bird / dragon / robot -> unsupported (never forced humanoid);
 *   - backPattern is metadata only (never fabricated as texture);
 *   - identical input always yields byte-identical SVG.
 *
 * The output is a "2D layered / Live2D-ready" asset, NOT an official Cubism
 * runtime model: no physics / parameter / deformer / motion.
 */

export const PORTRAIT_WIDTH = 400
export const PORTRAIT_HEIGHT = 600
export const PORTRAIT_MIME = 'image/svg+xml'

const LAYER_ORDER: Portrait2DLayerId[] = ['body', 'outfit', 'face', 'eyes', 'hair', 'accessory']

const DEFAULT_SKIN = '#E8CDB3'
const DEFAULT_HAIR = '#3E3A3A'
const DEFAULT_EYE = '#2B2B2B'
const DEFAULT_OUTFIT = '#6C8CFF'
const DEFAULT_OUTFIT_SECONDARY = '#3E4E8C'
const DEFAULT_OUTFIT_ACCENT = '#A55CFF'
const DEFAULT_BODY = '#D9C4A9'

/** Body types that produce a full humanoid front portrait. */
const FULL_HUMANOID_BODY_TYPES = new Set(['humanoid', 'biped-anthro'])

/** Body types that are intentionally unsupported this stage. */
const UNSUPPORTED_BODY_TYPES = new Set(['quadruped', 'bird', 'dragon', 'robot'])

interface RenderParams {
  skin: string
  hair: string
  eye: string
  outfitPrimary: string
  outfitSecondary: string
  outfitAccent: string
  body: string
}

/**
 * Resolve deterministic render colors. When no CharacterAsset is present (old
 * projects) every value falls back to the stable default - no guessing.
 */
function resolveRenderParams(asset: CharacterAsset | null | undefined): RenderParams {
  if (!asset) {
    return {
      skin: DEFAULT_SKIN,
      hair: DEFAULT_HAIR,
      eye: DEFAULT_EYE,
      outfitPrimary: DEFAULT_OUTFIT,
      outfitSecondary: DEFAULT_OUTFIT_SECONDARY,
      outfitAccent: DEFAULT_OUTFIT_ACCENT,
      body: DEFAULT_BODY
    }
  }
  const outfit = asset.outfitColors ?? []
  return {
    skin: asset.skinColor ?? DEFAULT_SKIN,
    hair: asset.hairColor ?? DEFAULT_HAIR,
    eye: asset.eyeColor ?? DEFAULT_EYE,
    outfitPrimary: outfit[0] ?? DEFAULT_OUTFIT,
    outfitSecondary: outfit[1] ?? DEFAULT_OUTFIT_SECONDARY,
    outfitAccent: outfit[2] ?? DEFAULT_OUTFIT_ACCENT,
    body: asset.skinColor ?? DEFAULT_BODY
  }
}

function sourceOf(asset: CharacterAsset | null | undefined, field: string): AssetSource {
  if (!asset) return 'derived'
  return asset.source?.[field] ?? 'derived'
}

/** layer id -> CharacterAsset field name for provenance lookup. */
const LAYER_SOURCE_FIELD: Record<Portrait2DLayerId, string> = {
  body: 'skinColor',
  outfit: 'outfitColors',
  face: 'skinColor',
  eyes: 'eyeColor',
  hair: 'hairColor',
  accessory: 'outfitColors'
}

function layerSource(asset: CharacterAsset | null | undefined, id: Portrait2DLayerId): AssetSource {
  return sourceOf(asset, LAYER_SOURCE_FIELD[id])
}

interface BodyLayers {
  body: string
  outfit: string
  face: string
  eyes: string
  hair: string
  accessory: string
}

function humanoidLayers(params: RenderParams, anatomy: AnatomyGraph): BodyLayers {
  // body: torso silhouette (skin-coloured base, then outfit over it).
  const body = `<ellipse cx="200" cy="330" rx="95" ry="150" fill="${params.body}"/>`
  const outfit = `<path d="M118 210 Q200 175 282 210 L296 470 Q200 500 104 470 Z" fill="${params.outfitPrimary}"/>`
  const face = `<ellipse cx="200" cy="150" rx="72" ry="88" fill="${params.skin}"/>`
  const eyes = [
    `<ellipse cx="168" cy="150" rx="13" ry="9" fill="${params.eye}"/>`,
    `<ellipse cx="232" cy="150" rx="13" ry="9" fill="${params.eye}"/>`
  ].join('')
  const hair = `<path d="M128 150 Q128 52 200 48 Q272 52 272 150 Q272 88 200 84 Q128 88 128 150 Z" fill="${params.hair}"/>`

  let accessory = ''
  if (anatomy.ears) {
    accessory += `<path d="M140 88 Q120 40 142 22 Q158 44 158 82 Z" fill="${params.hair}"/>`
    accessory += `<path d="M260 88 Q280 40 258 22 Q242 44 242 82 Z" fill="${params.hair}"/>`
  }
  if (anatomy.horns || anatomy.antlers) {
    accessory += `<path d="M150 70 Q138 22 150 4 Q164 22 164 58 Z" fill="${params.outfitAccent}"/>`
    accessory += `<path d="M250 70 Q262 22 250 4 Q236 22 236 58 Z" fill="${params.outfitAccent}"/>`
  }
  if (anatomy.wings) {
    accessory += `<path d="M112 240 Q40 220 52 340 Q96 330 116 300 Z" fill="${params.outfitAccent}" opacity="0.85"/>`
    accessory += `<path d="M288 240 Q360 220 348 340 Q304 330 284 300 Z" fill="${params.outfitAccent}" opacity="0.85"/>`
  }
  if (anatomy.tail === 'single' || anatomy.tail === 'multiple') {
    accessory += `<path d="M180 470 Q150 530 200 560 Q250 530 220 470 Z" fill="${params.outfitAccent}" opacity="0.9"/>`
  }

  return { body, outfit, face, eyes, hair, accessory }
}

function layersToSvg(layers: Portrait2DLayer[]): string {
  const body = layers
    .slice()
    .sort((a, b) => a.order - b.order)
    .map((l) => l.svg)
    .join('\n')
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${PORTRAIT_WIDTH}" height="${PORTRAIT_HEIGHT}" ` +
    `viewBox="0 0 ${PORTRAIT_WIDTH} ${PORTRAIT_HEIGHT}">\n` +
    body +
    '\n</svg>'
  )
}

/** Deterministic full humanoid front portrait. */
function buildFullPortrait(spec: CharacterSpec, asset: CharacterAsset | null | undefined): Portrait2DResult {
  const params = resolveRenderParams(asset)
  const layers = humanoidLayers(params, spec.anatomy)

  const layerDefs: Portrait2DLayer[] = LAYER_ORDER.map((id) => ({
    id,
    order: LAYER_ORDER.indexOf(id),
    svg: layers[id],
    sources: { [id]: layerSource(asset, id) }
  }))

  return toResult(spec, asset, layerDefs)
}

/**
 * custom body type: anatomy-driven partial portrait. Only layers that are
 * reliably expressible from the anatomy are emitted; never a forced humanoid.
 */
function buildCustomPortrait(spec: CharacterSpec, asset: CharacterAsset | null | undefined): Portrait2DResult {
  const params = resolveRenderParams(asset)
  const anatomy = spec.anatomy

  const present: Portrait2DLayer[] = []

  const hasHead = anatomy.hasHead !== false
  const hasTorso = anatomy.hasTorso !== false
  const hasFace = anatomy.hasFace !== false

  if (hasTorso) {
    present.push({
      id: 'body',
      order: 0,
      svg: `<ellipse cx="200" cy="330" rx="95" ry="150" fill="${params.body}"/>`,
      sources: { body: sourceOf(asset, 'skinColor') }
    })
    present.push({
      id: 'outfit',
      order: 1,
      svg: `<path d="M118 210 Q200 175 282 210 L296 470 Q200 500 104 470 Z" fill="${params.outfitPrimary}"/>`,
      sources: { outfit: sourceOf(asset, 'outfitColors') }
    })
  }
  if (hasHead && hasFace) {
    present.push({
      id: 'face',
      order: 2,
      svg: `<ellipse cx="200" cy="150" rx="72" ry="88" fill="${params.skin}"/>`,
      sources: { face: sourceOf(asset, 'skinColor') }
    })
    present.push({
      id: 'eyes',
      order: 3,
      svg:
        `<ellipse cx="168" cy="150" rx="13" ry="9" fill="${params.eye}"/>\n` +
        `<ellipse cx="232" cy="150" rx="13" ry="9" fill="${params.eye}"/>`,
      sources: { eyes: sourceOf(asset, 'eyeColor') }
    })
  }
  if (hasHead && asset?.hairColor) {
    present.push({
      id: 'hair',
      order: 4,
      svg: `<path d="M128 150 Q128 52 200 48 Q272 52 272 150 Q272 88 200 84 Q128 88 128 150 Z" fill="${params.hair}"/>`,
      sources: { hair: sourceOf(asset, 'hairColor') }
    })
  }
  // Appendages only when anatomy explicitly says so (never guessed).
  if (hasHead && (anatomy.ears || anatomy.horns || anatomy.antlers)) {
    const ears =
      anatomy.ears
        ? `<path d="M140 88 Q120 40 142 22 Q158 44 158 82 Z" fill="${params.hair}"/><path d="M260 88 Q280 40 258 22 Q242 44 242 82 Z" fill="${params.hair}"/>`
        : ''
    const horns =
      anatomy.horns || anatomy.antlers
        ? `<path d="M150 70 Q138 22 150 4 Q164 22 164 58 Z" fill="${params.outfitAccent}"/><path d="M250 70 Q262 22 250 4 Q236 22 236 58 Z" fill="${params.outfitAccent}"/>`
        : ''
    present.push({
      id: 'accessory',
      order: 5,
      svg: ears + horns,
      sources: { accessory: sourceOf(asset, 'hairColor') }
    })
  }
  if (hasTorso && anatomy.wings) {
    present.push({
      id: 'accessory',
      order: 5,
      svg:
        `<path d="M112 240 Q40 220 52 340 Q96 330 116 300 Z" fill="${params.outfitAccent}" opacity="0.85"/>` +
        `<path d="M288 240 Q360 220 348 340 Q304 330 284 300 Z" fill="${params.outfitAccent}" opacity="0.85"/>`,
      sources: { accessory: sourceOf(asset, 'outfitColors') }
    })
  }
  if (hasTorso && (anatomy.tail === 'single' || anatomy.tail === 'multiple')) {
    present.push({
      id: 'accessory',
      order: 5,
      svg: `<path d="M180 470 Q150 530 200 560 Q250 530 220 470 Z" fill="${params.outfitAccent}" opacity="0.9"/>`,
      sources: { accessory: sourceOf(asset, 'outfitColors') }
    })
  }

  return toResult(spec, asset, present)
}

function toResult(
  spec: CharacterSpec,
  asset: CharacterAsset | null | undefined,
  layerDefs: Portrait2DLayer[]
): Portrait2DResult {
  const descriptor = {
    version: 1 as const,
    kind: '2d-layered' as const,
    note: '2D layered / Live2D-ready，非 Cubism Runtime，不含 physics/parameter/motion' as const,
    width: PORTRAIT_WIDTH,
    height: PORTRAIT_HEIGHT,
    layers: layerDefs,
    frontView: true,
    backPattern: asset?.backPattern ?? null,
    assetSource: asset ?? emptyAsset(),
    cubism: { present: false as const }
  }

  return {
    svg: layersToSvg(layerDefs),
    descriptor,
    fileName: `${sanitizeName(spec.name) || 'AIVCS Character'}.svg`,
    mime: PORTRAIT_MIME
  }
}

function emptyAsset(): CharacterAsset {
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

function sanitizeName(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim()
}

/**
 * Entry point: build the 2D portrait output for a spec + asset.
 * Returns { status: 'ok', result } or { status: 'unsupported', ... }.
 */
export function buildPortrait2D(
  spec: CharacterSpec,
  asset?: CharacterAsset | null
): Portrait2DOutput {
  const bodyType = spec.bodyType ?? 'humanoid'

  if (UNSUPPORTED_BODY_TYPES.has(bodyType)) {
    return {
      status: 'unsupported',
      bodyType,
      reason: `${bodyType} 体型暂不支持 2D 立绘（本阶段仅 humanoid / biped-anthro / custom），不映射成人形模板。`
    }
  }

  if (FULL_HUMANOID_BODY_TYPES.has(bodyType)) {
    return { status: 'ok', result: buildFullPortrait(spec, asset) }
  }

  // custom: anatomy-driven partial portrait - only reliably expressible parts.
  return { status: 'ok', result: buildCustomPortrait(spec, asset) }
}
