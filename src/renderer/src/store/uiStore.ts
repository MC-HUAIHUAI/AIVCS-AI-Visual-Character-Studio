import { create } from 'zustand'
import { backendHealth } from '../core/providers/httpProvider'
import type { CameraPreset } from '../three/ViewportManager'
import { defaultAppSettings } from '../core/settings/appSettingsLogic'
import type { AppSettings, ProviderEndpointSettings } from '@shared/types'

interface UIState {
  backendOnline: boolean
  providerId: string
  cameraPreset: CameraPreset
  selectedReferenceIds: string[]
  /** Phase 3-5A: app-level provider settings (persisted via main process). */
  appSettings: AppSettings
  settingsOpen: boolean
  portrait2dOpen: boolean

  checkBackend: () => Promise<boolean>
  setProviderId: (id: string) => void
  setCameraPreset: (preset: CameraPreset) => void
  toggleReference: (id: string) => void
  clearReferences: () => void
  setExternal3D: (patch: Partial<ProviderEndpointSettings>) => void
  setVisionSettings: (patch: Partial<ProviderEndpointSettings>) => void
  loadAppSettings: () => Promise<void>
  saveAppSettings: () => Promise<{ ok: boolean; error?: string }>
  testProviderConnection: (kind: 'vision' | 'external3d') => Promise<{ ok: boolean; error?: string }>
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
  appSettings: defaultAppSettings(),
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
    set((s) => ({ appSettings: { ...s.appSettings, external3d: { ...s.appSettings.external3d, ...patch } } }))
  },

  setVisionSettings: (patch) => {
    set((s) => ({ appSettings: { ...s.appSettings, vision: { ...s.appSettings.vision, ...patch } } }))
  },

  loadAppSettings: async () => {
    const settings = await window.aivcs.loadAppSettings()
    set({ appSettings: settings })
  },

  saveAppSettings: async () => {
    const result = await window.aivcs.saveAppSettings(get().appSettings)
    return result
  },

  testProviderConnection: async (kind) => {
    return window.aivcs.testProviderConnection(kind, get().appSettings)
  },

  openSettings: () => set({ settingsOpen: true }),

  closeSettings: () => set({ settingsOpen: false }),

  openPortrait2D: () => set({ portrait2dOpen: true }),

  closePortrait2D: () => set({ portrait2dOpen: false })
}))
