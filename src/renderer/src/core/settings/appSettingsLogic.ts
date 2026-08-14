import type { AppSettings, ProviderEndpointSettings } from '@shared/types'

/**
 * Phase 3-5A: App-level provider settings logic.
 *
 * PURE logic only - no network, no IPC. Startup/load/save never connect; the
 * only network path is an explicit user-triggered "test connection" (handled by
 * the main process). API keys are never logged, never part of project data.
 */

export const DEFAULT_VISION_SETTINGS: ProviderEndpointSettings = {
  enabled: false,
  providerId: '',
  baseUrl: '',
  apiKey: ''
}

export const DEFAULT_EXTERNAL3D_SETTINGS: ProviderEndpointSettings = {
  enabled: false,
  providerId: '',
  baseUrl: '',
  apiKey: ''
}

export function defaultAppSettings(): AppSettings {
  return {
    version: 1,
    vision: { ...DEFAULT_VISION_SETTINGS },
    external3d: { ...DEFAULT_EXTERNAL3D_SETTINGS }
  }
}

export type ProviderStatus = 'unconfigured' | 'configured-disabled' | 'enabled'

/** Derive the human/provider status from settings (no network). */
export function providerStatus(p: ProviderEndpointSettings): ProviderStatus {
  if (p.enabled) return 'enabled'
  const hasKey = typeof p.apiKey === 'string' && p.apiKey.length > 0
  const hasUrl = typeof p.baseUrl === 'string' && p.baseUrl.length > 0
  if (hasKey || hasUrl) return 'configured-disabled'
  return 'unconfigured'
}

export function isBaseUrlFormatted(value: string): boolean {
  if (!value) return false
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export interface AppSettingsIssue {
  section: 'vision' | 'external3d'
  field: 'providerId' | 'baseUrl' | 'apiKey'
  message: string
}

/** Format-level validation; never contacts the network. */
export function validateAppSettings(settings: AppSettings): AppSettingsIssue[] {
  const issues: AppSettingsIssue[] = []
  const check = (section: 'vision' | 'external3d', p: ProviderEndpointSettings): void => {
    if (!p.enabled) return
    if (!p.providerId.trim()) {
      issues.push({ section, field: 'providerId', message: 'providerId 不能为空' })
    }
    if (!isBaseUrlFormatted(p.baseUrl)) {
      issues.push({ section, field: 'baseUrl', message: 'baseUrl 必须是 http(s) 地址' })
    }
    if (!p.apiKey) {
      issues.push({ section, field: 'apiKey', message: 'apiKey 不能为空（enabled 时必填）' })
    }
  }
  check('vision', settings.vision)
  check('external3d', settings.external3d)
  return issues
}

/** Redact an apiKey for any display/log surface (never show the real key). */
export function redactApiKey(key: string): string {
  if (!key) return ''
  if (key.length <= 6) return '***'
  return `${key.slice(0, 2)}***${key.slice(-2)}`
}

/** Sanitized settings snapshot safe to include in logs/exports (no keys). */
export function sanitizeSettings(settings: AppSettings): AppSettings {
  return {
    version: settings.version,
    vision: { ...settings.vision, apiKey: settings.vision.apiKey ? '***' : '' },
    external3d: { ...settings.external3d, apiKey: settings.external3d.apiKey ? '***' : '' }
  }
}

/** True when a provider is usable (enabled + key + baseUrl). */
export function isProviderUsable(p: ProviderEndpointSettings): boolean {
  return p.enabled && Boolean(p.apiKey) && isBaseUrlFormatted(p.baseUrl)
}

/** Build the connectivity-test endpoint URL for a provider (no key included). */
export function testConnectionUrl(p: ProviderEndpointSettings): string {
  return `${p.baseUrl.replace(/\/+$/, '')}/health`
}
