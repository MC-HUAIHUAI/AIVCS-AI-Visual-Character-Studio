import { contextBridge, ipcRenderer } from 'electron'
import { IPC_CHANNELS } from '../shared/types'
import type { AivcsApi } from '../shared/ipc'
import type {
  AppSettings,
  ProjectData,
  ProjectSaveResult,
  ProjectLoadResult,
  ImportImageResult,
  ExportModelResult
} from '../shared/types'

const api: AivcsApi = {
  saveProject: (project: ProjectData): Promise<ProjectSaveResult> =>
    ipcRenderer.invoke(IPC_CHANNELS.saveProject, project),
  loadProject: (): Promise<ProjectLoadResult> => ipcRenderer.invoke(IPC_CHANNELS.loadProject),
  importImages: (): Promise<ImportImageResult> => ipcRenderer.invoke(IPC_CHANNELS.importImages),
  exportModel: (dataUrl: string, defaultName: string): Promise<ExportModelResult> =>
    ipcRenderer.invoke(IPC_CHANNELS.exportModel, dataUrl, defaultName),
  pickExportPath: (defaultName: string): Promise<string | null> =>
    ipcRenderer.invoke(IPC_CHANNELS.pickExportPath, defaultName),
  loadAppSettings: (): Promise<AppSettings> => ipcRenderer.invoke(IPC_CHANNELS.settingsLoad),
  saveAppSettings: (settings: AppSettings): Promise<{ ok: boolean; error?: string }> =>
    ipcRenderer.invoke(IPC_CHANNELS.settingsSave, settings),
  testProviderConnection: (
    kind: 'vision' | 'external3d',
    settings: AppSettings
  ): Promise<{ ok: boolean; error?: string }> =>
    ipcRenderer.invoke(IPC_CHANNELS.settingsTestConnection, kind, settings),
  getDemoModel: (characterType: string): Promise<{ ok: boolean; bytes?: ArrayBuffer; error?: string }> =>
    ipcRenderer.invoke(IPC_CHANNELS.getDemoModel, characterType)
}

contextBridge.exposeInMainWorld('aivcs', api)
