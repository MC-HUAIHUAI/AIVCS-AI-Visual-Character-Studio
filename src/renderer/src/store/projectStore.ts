import { create } from 'zustand'
import type { CharacterAsset, CharacterSpec, ImageAsset, ModelAsset, ProjectData } from '@shared/types'
import {
  createProject,
  importImages as importImagesViaIpc,
  loadProject as loadProjectViaIpc,
  normalizeSpec,
  saveProject as saveProjectViaIpc
} from '../core/project/projectManager'
import { applyAssetPatch, deriveCharacterAsset } from '../core/spec/characterAssetLogic'

interface ProjectState {
  project: ProjectData
  selectedModelId: string | null
  selectedImageId: string | null
  isDirty: boolean
  saveError: string | null
  /** Runtime-only cache of loaded model bytes (not persisted to disk). */
  modelBuffers: Record<string, ArrayBuffer>

  newProject: (name: string) => void
  importImages: () => Promise<void>
  removeImage: (id: string) => void
  updateImage: (id: string, patch: Partial<ImageAsset>) => void
  addModel: (model: ModelAsset, buffer?: ArrayBuffer) => void
  removeModel: (id: string) => void
  updateSpec: (patch: Partial<CharacterSpec>) => void
  /** Phase 3-2: merge a confirmed vision assetPatch into project.characterAsset. */
  applyCharacterAssetPatch: (patch: Partial<CharacterAsset>) => void
  save: () => Promise<boolean>
  load: () => Promise<void>
  setDirty: (dirty: boolean) => void
  selectModel: (id: string | null) => void
  selectImage: (id: string | null) => void
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  project: createProject('Untitled Project'),
  selectedModelId: 'demo-character',
  selectedImageId: null,
  isDirty: false,
  saveError: null,
  modelBuffers: {},

  newProject: (name) => {
    set({ project: createProject(name), selectedModelId: 'demo-character', selectedImageId: null, isDirty: false, saveError: null })
  },

  importImages: async () => {
    const assets = await importImagesViaIpc()
    if (assets.length === 0) return
    const { project } = get()
    set({
      project: { ...project, images: [...project.images, ...assets], updatedAt: new Date().toISOString() },
      isDirty: true
    })
  },

  removeImage: (id) => {
    const { project, isDirty } = get()
    const images = project.images.filter((i) => i.id !== id)
    const spec = project.spec
    const referenceImageIds = spec.referenceImageIds.filter((rid) => rid !== id)
    set({
      project: {
        ...project,
        images,
        updatedAt: new Date().toISOString(),
        spec: { ...spec, referenceImageIds }
      },
      isDirty: isDirty || images.length !== project.images.length,
      selectedImageId: get().selectedImageId === id ? null : get().selectedImageId
    })
  },

  updateImage: (id, patch) => {
    const { project } = get()
    const images = project.images.map((img) => (img.id === id ? { ...img, ...patch } : img))
    set({
      project: { ...project, images, updatedAt: new Date().toISOString() },
      isDirty: true
    })
  },

  addModel: (model, buffer) => {
    const { project, modelBuffers } = get()
    set({
      project: { ...project, models: [model, ...project.models], updatedAt: new Date().toISOString() },
      selectedModelId: model.id,
      modelBuffers: buffer ? { ...modelBuffers, [model.id]: buffer } : modelBuffers,
      isDirty: true
    })
  },

  removeModel: (id) => {
    const { project, selectedModelId } = get()
    if (project.models.length <= 1) return
    const models = project.models.filter((m) => m.id !== id)
    set({
      project: { ...project, models, updatedAt: new Date().toISOString() },
      selectedModelId: selectedModelId === id ? (models[0]?.id ?? null) : selectedModelId,
      isDirty: true
    })
  },

  updateSpec: (patch) => {
    const { project } = get()
    set({
      project: {
        ...project,
        spec: { ...project.spec, ...patch, updatedAt: new Date().toISOString() },
        updatedAt: new Date().toISOString()
      },
      isDirty: true
    })
  },

  applyCharacterAssetPatch: (patch) => {
    const { project } = get()
    const base = project.characterAsset ?? deriveCharacterAsset(project.spec)
    const next = applyAssetPatch(base, patch)
    set({
      project: { ...project, characterAsset: next, updatedAt: new Date().toISOString() },
      isDirty: true
    })
  },

  save: async () => {
    const result = await saveProjectViaIpc(get().project)
    if (result.ok) {
      set({ isDirty: false, saveError: null })
      return true
    }
    set({ saveError: result.error ?? 'Save failed' })
    return false
  },

  load: async () => {
    const result = await loadProjectViaIpc()
    if (!result.ok || !result.project) {
      if (result.error && result.error !== 'cancelled') set({ saveError: result.error })
      return
    }
    set({
      project: { ...result.project, spec: normalizeSpec(result.project.spec) },
      selectedModelId: result.project.models[0]?.id ?? null,
      selectedImageId: null,
      isDirty: false,
      saveError: null
    })
  },

  setDirty: (dirty) => set({ isDirty: dirty }),
  selectModel: (id) => set({ selectedModelId: id }),
  selectImage: (id) => set({ selectedImageId: id })
}))
