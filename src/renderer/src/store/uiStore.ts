import { create } from 'zustand'
import { backendHealth } from '../core/providers/httpProvider'
import type { CameraPreset } from '../three/ViewportManager'

interface UIState {
  backendOnline: boolean
  providerId: string
  cameraPreset: CameraPreset
  selectedReferenceIds: string[]

  checkBackend: () => Promise<boolean>
  setProviderId: (id: string) => void
  setCameraPreset: (preset: CameraPreset) => void
  toggleReference: (id: string) => void
  clearReferences: () => void
}

export const useUIStore = create<UIState>((set, get) => ({
  backendOnline: false,
  providerId: 'mock-local',
  cameraPreset: 'iso',
  selectedReferenceIds: [],

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

  clearReferences: () => set({ selectedReferenceIds: [] })
}))
