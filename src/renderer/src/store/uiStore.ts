import { create } from 'zustand'
import { backendHealth } from '../core/providers/httpProvider'
import type { CameraPreset } from '../three/ViewportManager'
import { DEFAULT_EXTERNAL3D_SETTINGS } from '../core/settings/external3dSettingsLogic'
import type { External3DProviderSettings } from '@shared/types'

interface UIState {
  backendOnline: boolean
  providerId: string
  cameraPreset: CameraPreset
  selectedReferenceIds: string[]
  /** Phase 2.4-D-pre: reserved external 3D provider contract (in-memory only). */
  external3d: External3DProviderSettings
  settingsOpen: boolean
  portrait2dOpen: boolean

  checkBackend: () => Promise<boolean>
  setProviderId: (id: string) => void
  setCameraPreset: (preset: CameraPreset) => void
  toggleReference: (id: string) => void
  clearReferences: () => void
  setExternal3D: (patch: Partial<External3DProviderSettings>) => void
  openSettings: () => void
  closeSettings: () => void
  openPortrait2D: () => void
  closePortrait2D: () => void
}

export const useUIStore = create<UIState>((set, get) => ({
  backendOnline: false,
  providerId: 'mock-local',
  cameraPreset: 'iso',
  selectedReferenceIds: [],
  external3d: { ...DEFAULT_EXTERNAL3D_SETTINGS },
  settingsOpen: false,
  portrait2dOpen: false,

  checkBackend: async () => {
    const online = await backendHealth()
    set({ backendOnline: online })
    return online
  },

  setProviderId: (id) => set({ providerId: id }),

  setCameraPreset: (preset) => {
    set({ cameraPreset: preset })
  },

  toggleReference: (id) => {
    const { selectedReferenceIds } = get()
    const next = selectedReferenceIds.includes(id)
      ? selectedReferenceIds.filter((r) => r !== id)
      : [...selectedReferenceIds, id]
    set({ selectedReferenceIds: next })
  },

  clearReferences: () => set({ selectedReferenceIds: [] }),

  setExternal3D: (patch) => {
    set((s) => ({ external3d: { ...s.external3d, ...patch } }))
  },

  openSettings: () => set({ settingsOpen: true }),

  closeSettings: () => set({ settingsOpen: false }),

  openPortrait2D: () => set({ portrait2dOpen: true }),

  closePortrait2D: () => set({ portrait2dOpen: false })
}))
