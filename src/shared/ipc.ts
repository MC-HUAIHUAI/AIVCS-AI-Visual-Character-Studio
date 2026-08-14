import type {
  ProjectData,
  ProjectSaveResult,
  ProjectLoadResult,
  ImportImageResult,
  ExportModelResult,
  AppSettings
} from './types'

/**
 * The API surface exposed to the renderer through the preload bridge.
 * Kept intentionally small: file system and OS dialogs live in the main process.
 */
export interface AivcsApi {
  saveProject(project: ProjectData): Promise<ProjectSaveResult>
  loadProject(): Promise<ProjectLoadResult>
  importImages(): Promise<ImportImageResult>
  /** Opens a save dialog and writes the given base64-encoded file contents. */
  exportModel(dataUrl: string, defaultName: string): Promise<ExportModelResult>
  /** Opens a save dialog and returns the chosen path (null when cancelled). */
  pickExportPath(defaultName: string): Promise<string | null>
  /** Loads app-level settings (safeStorage-decrypted apiKey only inside main). */
  loadAppSettings(): Promise<AppSettings>
  /** Persists app-level settings; apiKey encrypted at rest in main. */
  saveAppSettings(settings: AppSettings): Promise<{ ok: boolean; error?: string }>
  /**
   * User-initiated connectivity test. Only this call may produce a network
   * request; startup/load/save never do.
   */
  testProviderConnection(
    kind: 'vision' | 'external3d',
    settings: AppSettings
  ): Promise<{ ok: boolean; error?: string }>
}
