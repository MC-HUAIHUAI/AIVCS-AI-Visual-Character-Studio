import { app, ipcMain, safeStorage } from 'electron'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { IPC_CHANNELS } from '../shared/types'
import type { AppSettings, ProviderEndpointSettings } from '../shared/types'

/**
 * Phase 3-5A: App-level provider settings.
 *
 * - Persisted to app.getPath('userData')/app-settings.json;
 * - apiKey is encrypted at rest with Electron safeStorage (no third-party deps);
 * - API keys are never logged, never returned by IPC responses, never included
 *   in any project/export data;
 * - loading / saving settings performs NO network requests;
 * - the only network path is an explicit, user-triggered "test connection".
 */

const SETTINGS_FILE = () => join(app.getPath('userData'), 'app-settings.json')

const LOCAL_BACKEND = 'http://127.0.0.1:8321'

/**
 * Runtime-config auth token path (pure, testable).
 * - AIVCS_RUNTIME_TOKEN_FILE env wins (packaged launcher may set it).
 * - Packaged: userData/runtime_config_token.
 * - Dev: <appPath>/backend/data/runtime_config_token (backend default).
 */
export function resolveRuntimeTokenFile(
  opts: { env: string; isPackaged: boolean; userData: string; appPath: string }
): string {
  if (opts.env) return opts.env
  if (opts.isPackaged) return join(opts.userData, 'runtime_config_token')
  return join(opts.appPath, 'backend', 'data', 'runtime_config_token')
}

const RUNTIME_TOKEN_FILE = () => resolveRuntimeTokenFile({
  env: process.env['AIVCS_RUNTIME_TOKEN_FILE'] ?? '',
  isPackaged: app.isPackaged,
  userData: app.getPath('userData'),
  appPath: app.getAppPath()
})

function readRuntimeToken(): string {
  try {
    const path = RUNTIME_TOKEN_FILE()
    if (existsSync(path)) {
      return readFileSync(path, 'utf-8').trim()
    }
    // Packaged fallback: also check the dev-style location if it exists.
    if (app.isPackaged) {
      const dev = join(app.getAppPath(), 'backend', 'data', 'runtime_config_token')
      if (existsSync(dev)) return readFileSync(dev, 'utf-8').trim()
    }
  } catch {
    return ''
  }
  return ''
}

/** Push Vision App Settings into the local backend runtime config (127.0.0.1, POST, token-guarded). */
async function pushVisionConfigToBackend(settings: AppSettings): Promise<{ ok: boolean; error?: string }> {
  const v = settings.vision
  if (!v.enabled || !v.apiKey || !v.baseUrl) return { ok: true }
  const token = readRuntimeToken()
  if (!token) return { ok: true, error: '后端运行时配置令牌不可用（后端未启动？）' }
  try {
    const res = await fetch(`${LOCAL_BACKEND}/api/v1/config/vision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-aivcs-config-token': token },
      body: JSON.stringify({ baseUrl: v.baseUrl, model: '', apiKey: v.apiKey })
    })
    if (!res.ok) return { ok: false, error: `配置推送失败（HTTP ${res.status}）` }
    return { ok: true }
  } catch {
    return { ok: false, error: '后端离线，无法推送运行时配置' }
  }
}

export function defaultAppSettings(): AppSettings {
  return {
    version: 1,
    vision: { enabled: false, providerId: '', baseUrl: '', apiKey: '' },
    external3d: { enabled: false, providerId: '', baseUrl: '', apiKey: '' }
  }
}

/** Redact an apiKey for logging (never log real keys). */
function redact(key: string): string {
  if (!key) return ''
  return `${key.slice(0, 2)}***${key.slice(-2)}`
}

function encryptSecret(plain: string): string {
  if (!plain) return ''
  try {
    if (!safeStorage.isEncryptionAvailable()) {
      // Fallback: store base64 marker only when OS secure storage is unavailable.
      // Still never logs / never returns the raw key in IPC responses.
      return `plain:${Buffer.from(plain, 'utf-8').toString('base64')}`
    }
    return `enc:${safeStorage.encryptString(plain).toString('base64')}`
  } catch {
    return ''
  }
}

function decryptSecret(stored: string): string {
  if (!stored) return ''
  try {
    if (stored.startsWith('enc:')) {
      const buf = Buffer.from(stored.slice(4), 'base64')
      return safeStorage.decryptString(buf)
    }
    if (stored.startsWith('plain:')) {
      return Buffer.from(stored.slice(6), 'base64').toString('utf-8')
    }
  } catch {
    return ''
  }
  return ''
}

function normalize(parsed: Partial<AppSettings> | null | undefined): AppSettings {
  const def = defaultAppSettings()
  if (!parsed || typeof parsed !== 'object') return def
  const pick = (src: Partial<ProviderEndpointSettings> | undefined): ProviderEndpointSettings => ({
    enabled: Boolean(src?.enabled),
    providerId: typeof src?.providerId === 'string' ? src.providerId : '',
    baseUrl: typeof src?.baseUrl === 'string' ? src.baseUrl : '',
    apiKey: typeof src?.apiKey === 'string' ? src.apiKey : ''
  })
  return {
    version: 1,
    vision: pick(parsed.vision),
    external3d: pick(parsed.external3d)
  }
}

function loadFromDisk(): AppSettings {
  const path = SETTINGS_FILE()
  if (!existsSync(path)) return defaultAppSettings()
  try {
    const raw = JSON.parse(readFileSync(path, 'utf-8')) as AppSettings
    return normalize(raw)
  } catch {
    return defaultAppSettings()
  }
}

/** Decrypted settings (used internally for runtime push / test only). */
export function loadAppSettings(): AppSettings {
  const raw = loadFromDisk()
  return {
    version: 1,
    vision: { ...raw.vision, apiKey: decryptSecret(raw.vision.apiKey) },
    external3d: { ...raw.external3d, apiKey: decryptSecret(raw.external3d.apiKey) }
  }
}

export function saveAppSettings(settings: AppSettings): { ok: boolean; error?: string } {
  try {
    const normalized = normalize(settings)
    const toDisk: AppSettings = {
      version: 1,
      vision: { ...normalized.vision, apiKey: encryptSecret(normalized.vision.apiKey) },
      external3d: { ...normalized.external3d, apiKey: encryptSecret(normalized.external3d.apiKey) }
    }
    writeFileSync(SETTINGS_FILE(), JSON.stringify(toDisk, null, 2), { encoding: 'utf-8', mode: 0o600 })
    // Best-effort runtime push with the REAL key (read back decrypted).
    void pushVisionConfigToBackend(loadAppSettings())
    return { ok: true }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) }
  }
}

/**
 * User-initiated connectivity test. This is the ONLY place a network request is
 * allowed for settings. Bound to the local backend / provider endpoint only.
 */
export async function testProviderConnection(
  kind: 'vision' | 'external3d',
  settings: AppSettings
): Promise<{ ok: boolean; error?: string }> {
  const provider = kind === 'vision' ? settings.vision : settings.external3d
  if (!provider.enabled) {
    return { ok: false, error: 'Provider 未启用' }
  }
  if (!provider.baseUrl) {
    return { ok: false, error: '缺少 baseUrl' }
  }

  if (kind === 'vision') {
    // Keyed probe goes through the local backend so the apiKey never leaves the
    // main -> backend chain and is never returned. Use the stored real key.
    const stored = loadAppSettings()
    const push = await pushVisionConfigToBackend(stored)
    if (!push.ok) return push
    const token = readRuntimeToken()
    if (!token) return { ok: false, error: '后端运行时配置令牌不可用' }
    try {
      const res = await fetch(`${LOCAL_BACKEND}/api/v1/config/vision/test`, {
        method: 'POST',
        headers: { 'x-aivcs-config-token': token }
      })
      const body = (await res.json().catch(() => ({}))) as { detail?: string }
      if (!res.ok) return { ok: false, error: body.detail ?? `HTTP ${res.status}` }
      return { ok: true }
    } catch {
      return { ok: false, error: '后端离线，无法测试连接' }
    }
  }

  // external3d: reachability probe only (provider itself not implemented yet).
  const url = provider.baseUrl.replace(/\/+$/, '')
  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 8000)
    const res = await fetch(`${url}/health`, { signal: controller.signal, method: 'GET' })
    clearTimeout(timer)
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` }
    return { ok: true }
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error && err.name === 'AbortError' ? '连接超时' : '无法连接（provider 可能不可用）'
    }
  }
}

function registerSettingsHandlers(): void {
  ipcMain.handle(IPC_CHANNELS.settingsLoad, (): AppSettings => {
    // Renderer gets masked apiKeys only.
    const s = loadAppSettings()
    return {
      version: 1,
      vision: { ...s.vision, apiKey: redact(s.vision.apiKey) },
      external3d: { ...s.external3d, apiKey: redact(s.external3d.apiKey) }
    }
  })

  ipcMain.handle(
    IPC_CHANNELS.settingsSave,
    (_event, settings: AppSettings): { ok: boolean; error?: string } => saveAppSettings(settings)
  )

  ipcMain.handle(
    IPC_CHANNELS.settingsTestConnection,
    (_event, kind: 'vision' | 'external3d', settings: AppSettings) => testProviderConnection(kind, settings)
  )
}

export { registerSettingsHandlers }
