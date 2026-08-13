import { contextBridge, ipcRenderer } from 'electron'
import { IPC_CHANNELS } from '../shared/types'
import type { AivcsApi } from '../shared/ipc'
import type {
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
    ipcRenderer.invoke(IPC_CHANNELS.pickExportPath, defaultName)
}

contextBridge.exposeInMainWorld('aivcs', api)
