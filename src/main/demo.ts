import { app, ipcMain } from 'electron'
import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { IPC_CHANNELS } from '../shared/types'

/**
 * Phase 3-5C fix: serve built-in demo GLB bytes to the renderer over IPC.
 *
 * The renderer cannot `fetch('/demo_character.glb')` under the packaged
 * file:// protocol (web platforms forbid fetch on file:// URLs). Instead the
 * main process reads the whitelisted demo asset and returns its bytes.
 *
 * Security:
 *   - only the whitelisted demo keys are accepted (never an arbitrary path);
 *   - no network; no webSecurity change; no CSP change.
 */

const DEMO_RESOURCES: Record<string, string> = {
  human: 'demo_character.glb',
  creature: 'demo_fox.glb'
}

/** Resolve a bundled resource: packaged extraResources first, dev assets fallback. */
function demoPath(fileName: string): string {
  // Packaged: <install>/resources/assets/<file> (see electron-builder.yml).
  const packaged = join(app.getAppPath(), '..', 'assets', fileName)
  if (app.isPackaged && existsSync(packaged)) return packaged
  // Dev: <repo>/assets/<file>.
  return join(app.getAppPath(), 'assets', fileName)
}

function readDemoBytes(key: string): Buffer | null {
  const fileName = DEMO_RESOURCES[key]
  if (!fileName) return null
  const path = demoPath(fileName)
  if (!existsSync(path)) return null
  try {
    return readFileSync(path)
  } catch {
    return null
  }
}

function registerDemoHandlers(): void {
  ipcMain.handle(
    IPC_CHANNELS.getDemoModel,
    (_event, characterType: unknown): { ok: boolean; bytes?: ArrayBuffer; error?: string } => {
      // Whitelist only the predefined demo keys.
      const key = typeof characterType === 'string' ? characterType : ''
      if (key !== 'human' && key !== 'creature') {
        return { ok: false, error: 'invalid demo key' }
      }
      const buf = readDemoBytes(key)
      if (!buf) {
        return { ok: false, error: 'demo model unavailable' }
      }
      // Transfer as ArrayBuffer (structured clone is safe over IPC).
      const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer
      return { ok: true, bytes: ab }
    }
  )
}

export { registerDemoHandlers }
