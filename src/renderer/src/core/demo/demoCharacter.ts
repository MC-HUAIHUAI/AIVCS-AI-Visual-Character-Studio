import type { CharacterType, ModelAsset } from '@shared/types'

/**
 * Built-in demo characters bundled with the renderer. They are the default
 * scene assets and are what the mock providers hand back as their "generated"
 * result. Two demos prove that the same pipeline handles human AND non-human
 * characters: the human chibi and a biped anthro fox.
 */
export const DEMO_CHARACTER: ModelAsset = {
  id: 'demo-character',
  name: '演示角色（人类）',
  source: 'demo',
  format: 'glb',
  filePath: null,
  addedAt: new Date().toISOString()
}

export const DEMO_FOX: ModelAsset = {
  id: 'demo-fox',
  name: '演示角色（兽人狐）',
  source: 'demo',
  format: 'glb',
  filePath: null,
  addedAt: new Date().toISOString()
}

export const DEMO_CHARACTER_URL = '/demo_character.glb'
export const DEMO_FOX_URL = '/demo_fox.glb'

const DEMO_BY_ID: Record<string, string> = {
  [DEMO_CHARACTER.id]: DEMO_CHARACTER_URL,
  [DEMO_FOX.id]: DEMO_FOX_URL
}

/** Character types that are treated as non-human for demo asset selection. */
export const NON_HUMAN_TYPES: ReadonlySet<CharacterType> = new Set([
  'anthro',
  'animal',
  'fantasy-creature',
  'robot',
  'alien',
  'custom'
])

export function isNonHuman(characterType: CharacterType): boolean {
  return NON_HUMAN_TYPES.has(characterType)
}

export function demoUrlForId(id: string): string | null {
  return DEMO_BY_ID[id] ?? null
}

/** Chooses the demo GLB that best matches a character type. */
export function demoUrlForType(characterType: CharacterType): string {
  return isNonHuman(characterType) ? DEMO_FOX_URL : DEMO_CHARACTER_URL
}

export async function fetchBytes(url: string): Promise<ArrayBuffer> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Failed to fetch ${url} (HTTP ${res.status})`)
  return res.arrayBuffer()
}

export async function loadDemoCharacterBytes(id: string): Promise<ArrayBuffer> {
  const url = demoUrlForId(id)
  if (!url) throw new Error(`Unknown demo character id: ${id}`)
  return fetchBytes(url)
}
