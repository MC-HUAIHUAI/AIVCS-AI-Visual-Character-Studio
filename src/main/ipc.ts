import { dialog, ipcMain, nativeImage } from 'electron'
import { readFileSync, writeFileSync } from 'node:fs'
import { basename, extname } from 'node:path'
import { IPC_CHANNELS } from '../shared/types'
import type {
  ImageAsset,
  ProjectData,
  ProjectLoadResult,
  ProjectSaveResult,
  ImportImageResult,
  ExportModelResult
} from '../shared/types'

const IMAGE_FILTERS = [
  { name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp'] }
]

const MIME_BY_EXT: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp'
}

interface ExportFormat {
  name: string
  extensions: string[]
}

const EXPORT_FORMATS: Record<string, ExportFormat> = {
  '.glb': { name: 'glTF Binary', extensions: ['glb'] },
  '.gltf': { name: 'glTF', extensions: ['gltf'] },
  '.vrm': { name: 'VRM', extensions: ['vrm'] },
  '.svg': { name: 'SVG', extensions: ['svg'] }
}

/** Picks the export format descriptor from the requested default file name. */
function exportFormatFor(defaultName: string): ExportFormat {
  const lower = defaultName.toLowerCase()
  for (const ext of ['.vrm', '.glb', '.gltf', '.svg']) {
    if (lower.endsWith(ext)) return EXPORT_FORMATS[ext]
  }
  return EXPORT_FORMATS['.glb']
}

/** Ensures defaultName carries the extension that matches its format. */
function defaultPathFor(defaultName: string): string {
  const format = exportFormatFor(defaultName)
  const ext = format.extensions[0]
  return defaultName.toLowerCase().endsWith(`.${ext}`) ? defaultName : `${defaultName || 'character'}.${ext}`
}

function newId(): string {
  return `id_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

function dataUrlOf(buffer: Buffer, mime: string): string {
  return `data:${mime};base64,${buffer.toString('base64')}`
}

function registerProjectHandlers(): void {
  ipcMain.handle(IPC_CHANNELS.saveProject, async (_event, project: ProjectData): Promise<ProjectSaveResult> => {
    const defaultPath = `${sanitize(project.name) || 'untitled'}.aivcsproj.json`
    const result = await dialog.showSaveDialog({
      title: 'Save Project',
      defaultPath,
      filters: [{ name: 'AIVCS Project', extensions: ['aivcsproj.json'] }, { name: 'JSON', extensions: ['json'] }]
    })
    if (result.canceled || !result.filePath) return { ok: false, error: 'cancelled' }
    try {
      writeFileSync(result.filePath, JSON.stringify(project, null, 2), 'utf-8')
      return { ok: true, path: result.filePath }
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) }
    }
  })

  ipcMain.handle(IPC_CHANNELS.loadProject, async (): Promise<ProjectLoadResult> => {
    const result = await dialog.showOpenDialog({
      title: 'Open Project',
      properties: ['openFile'],
      filters: [{ name: 'AIVCS Project', extensions: ['aivcsproj.json', 'json'] }]
    })
    if (result.canceled || result.filePaths.length === 0) return { ok: false, error: 'cancelled' }
    const filePath = result.filePaths[0]
    try {
      const raw = JSON.parse(readFileSync(filePath, 'utf-8')) as ProjectData
      if (raw.version !== 1) return { ok: false, error: `Unsupported project version: ${raw.version}` }
      return { ok: true, project: raw, path: filePath }
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) }
    }
  })

  ipcMain.handle(IPC_CHANNELS.importImages, async (): Promise<ImportImageResult> => {
    const result = await dialog.showOpenDialog({
      title: 'Import Images',
      properties: ['openFile', 'multiSelections'],
      filters: IMAGE_FILTERS
    })
    if (result.canceled || result.filePaths.length === 0) return { ok: true, assets: [] }
    try {
      const assets: ImageAsset[] = result.filePaths.map((filePath) => {
        const ext = extname(filePath).toLowerCase()
        const mime = MIME_BY_EXT[ext] ?? 'image/png'
        const buffer = readFileSync(filePath)
        const img = nativeImage.createFromPath(filePath)
        const size = img.isEmpty() ? { width: 0, height: 0 } : img.getSize()
        return {
          id: newId(),
          name: basename(filePath),
          mime,
          width: size.width,
          height: size.height,
          dataUrl: dataUrlOf(buffer, mime),
          bytes: buffer.length,
          addedAt: new Date().toISOString()
        }
      })
      return { ok: true, assets }
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) }
    }
  })

  ipcMain.handle(
    IPC_CHANNELS.exportModel,
    async (_event, dataUrl: string, defaultName: string): Promise<ExportModelResult> => {
      const format = exportFormatFor(defaultName)
      const result = await dialog.showSaveDialog({
        title: 'Export Model',
        defaultPath: defaultPathFor(defaultName),
        filters: [format]
      })
      if (result.canceled || !result.filePath) return { ok: false, error: 'cancelled' }
      try {
        const base64 = dataUrl.split(',')[1]
        if (!base64) throw new Error('Invalid data URL')
        writeFileSync(result.filePath, Buffer.from(base64, 'base64'))
        return { ok: true, path: result.filePath }
      } catch (err) {
        return { ok: false, error: err instanceof Error ? err.message : String(err) }
      }
    }
  )

  ipcMain.handle(IPC_CHANNELS.pickExportPath, async (_event, defaultName: string): Promise<string | null> => {
    const format = exportFormatFor(defaultName)
    const result = await dialog.showSaveDialog({
      title: 'Choose Export Location',
      defaultPath: defaultPathFor(defaultName),
      filters: [format]
    })
    return result.canceled || !result.filePath ? null : result.filePath
  })
}

function sanitize(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim()
}

export { registerProjectHandlers }
