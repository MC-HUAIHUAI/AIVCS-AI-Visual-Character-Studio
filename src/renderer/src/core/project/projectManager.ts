import type {
  AnatomyGraph,
  AppearanceProfile,
  CharacterSpec,
  FurProfile,
  ImageAsset,
  ProjectData,
  ProjectLoadResult,
  ProjectSaveResult,
  SpeciesInfo
} from '@shared/types'
import { DEMO_CHARACTER, DEMO_FOX } from '../demo/demoCharacter'

export function newId(): string {
  return `id_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

export function defaultSpecies(): SpeciesInfo {
  return { primary: 'custom', secondary: null, confidence: null, label: null }
}

export function defaultAnatomy(): AnatomyGraph {
  return {
    hasHead: true,
    hasFace: true,
    hasTorso: true,
    hasLimbs: true,
    tail: 'none',
    wings: false,
    ears: true,
    horns: false,
    antlers: false,
    snout: false,
    muzzle: false,
    beak: false,
    paws: false,
    claws: false,
    hooves: false,
    fins: false,
    tentacles: false,
    extraLimbs: false,
    customAppendages: []
  }
}

export function defaultFur(): FurProfile {
  return { enabled: false, style: 'stylized', length: 'medium', colors: [], patterns: [] }
}

export function defaultAppearance(): AppearanceProfile {
  return { baseColor: null, secondaryColors: [], patterns: [], markings: [] }
}

/**
 * Ensures a spec (possibly loaded from an older project file) carries every
 * field the app expects. Old projects that predate non-human support get the
 * new fields backfilled with defaults.
 */
export function normalizeSpec(spec: CharacterSpec): CharacterSpec {
  return {
    id: spec.id ?? newId(),
    name: spec.name ?? '未命名角色',
    style: spec.style ?? 'stylized',
    gender: spec.gender ?? 'neutral',
    heightCm: spec.heightCm ?? 160,
    description: spec.description ?? '',
    referenceImageIds: spec.referenceImageIds ?? [],
    tags: spec.tags ?? [],
    createdAt: spec.createdAt ?? new Date().toISOString(),
    updatedAt: spec.updatedAt ?? new Date().toISOString(),
    characterType: spec.characterType ?? 'human',
    species: spec.species ?? defaultSpecies(),
    bodyType: spec.bodyType ?? 'humanoid',
    anatomy: { ...defaultAnatomy(), ...(spec.anatomy ?? {}) },
    fur: { ...defaultFur(), ...(spec.fur ?? {}) },
    appearance: { ...defaultAppearance(), ...(spec.appearance ?? {}) }
  }
}

export function createDefaultSpec(): CharacterSpec {
  const now = new Date().toISOString()
  return {
    id: newId(),
    name: '未命名角色',
    style: 'stylized',
    gender: 'female',
    heightCm: 160,
    description: '',
    referenceImageIds: [],
    tags: [],
    createdAt: now,
    updatedAt: now,
    characterType: 'human',
    species: defaultSpecies(),
    bodyType: 'humanoid',
    anatomy: defaultAnatomy(),
    fur: defaultFur(),
    appearance: defaultAppearance()
  }
}

export function createProject(name: string): ProjectData {
  const now = new Date().toISOString()
  return {
    version: 1,
    name: name || '未命名项目',
    createdAt: now,
    updatedAt: now,
    spec: createDefaultSpec(),
    images: [],
    models: [{ ...DEMO_CHARACTER }, { ...DEMO_FOX }]
  }
}

export async function importImages(): Promise<ImageAsset[]> {
  const result = await window.aivcs.importImages()
  if (!result.ok) {
    if (result.error && result.error !== 'cancelled') console.warn('Import failed:', result.error)
    return []
  }
  return result.assets ?? []
}

export async function saveProject(project: ProjectData): Promise<ProjectSaveResult> {
  return window.aivcs.saveProject(project)
}

export async function loadProject(): Promise<ProjectLoadResult> {
  return window.aivcs.loadProject()
}
