import { app } from 'electron'
import { spawn, ChildProcess } from 'node:child_process'
import { join } from 'node:path'
import { existsSync } from 'node:fs'
import { createConnection } from 'node:net'
import { execFile } from 'node:child_process'

/**
 * Phase 3-5C: manage the Python backend process lifecycle.
 *
 * - Packaged: spawn resources/backend/backend.exe (PyInstaller onefile).
 * - Dev: reuse the user's manually started `npm run backend` on :8321 if
 *   already up; otherwise spawn `python -m uvicorn ...` as a fallback helper.
 * - Always listens on 127.0.0.1:8321 only; never external.
 * - On app quit the backend child is terminated.
 */

export const BACKEND_PORT = 8321
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`

let child: ChildProcess | null = null

function backendExePath(): string {
  return join(app.getAppPath(), '..', 'backend', 'backend.exe')
}

function isPortOpen(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = createConnection({ port, host: '127.0.0.1' })
    socket.setTimeout(500)
    socket.once('connect', () => {
      socket.destroy()
      resolve(true)
    })
    socket.once('error', () => resolve(false))
    socket.once('timeout', () => {
      socket.destroy()
      resolve(false)
    })
  })
}

function backendEnv(): NodeJS.ProcessEnv {
  return {
    ...process.env,
    AIVCS_DATA_DIR: join(app.getPath('userData'), 'data'),
    AIVCS_RUNTIME_TOKEN_FILE: join(app.getPath('userData'), 'data', 'runtime_config_token'),
    AIVCS_LOCAL3D_RIG_ENABLED: 'true'
  }
}

/**
 * Ensures the backend is reachable on 127.0.0.1:8321, starting it when needed.
 * Returns true when ready (or already running).
 */
export async function ensureBackend(): Promise<boolean> {
  if (await isPortOpen(BACKEND_PORT)) {
    return true
  }
  if (!app.isPackaged) {
    // Dev: instruct the user to run `npm run backend`; do not spawn python here
    // to avoid surprising them with an implicit process. Return quickly.
    return false
  }
  const exe = backendExePath()
  if (!existsSync(exe)) {
    console.error('backend.exe not found at', exe)
    return false
  }
  try {
    child = spawn(exe, [], {
      env: backendEnv(),
      stdio: 'ignore',
      windowsHide: true
    })
    child.on('error', (err) => {
      console.error('backend spawn failed:', err)
    })
    child.on('exit', (code) => {
      if (code !== 0) console.error('backend exited with code', code)
      child = null
    })
    // Wait up to ~15s for readiness.
    const deadline = Date.now() + 15000
    while (Date.now() < deadline) {
      if (await isPortOpen(BACKEND_PORT)) return true
      await new Promise((r) => setTimeout(r, 300))
    }
    return false
  } catch (err) {
    console.error('backend start failed:', err)
    return false
  }
}

export function stopBackend(): void {
  if (child && child.pid) {
    // backend.exe is a PyInstaller onefile: killing the bootloader pid alone may
    // leave its child alive. On Windows terminate the whole process tree.
    if (process.platform === 'win32') {
      try {
        execFile('taskkill', ['/pid', String(child.pid), '/T', '/F'], () => undefined)
      } catch {
        child.kill()
      }
    } else {
      child.kill()
    }
    child = null
  }
}

export { BACKEND_URL }
