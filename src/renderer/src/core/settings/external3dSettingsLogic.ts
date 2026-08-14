import type { ProviderEndpointSettings } from '@shared/types'
import {
  DEFAULT_EXTERNAL3D_SETTINGS,
  isBaseUrlFormatted,
  providerStatus,
  redactApiKey
} from './appSettingsLogic'

/**
 * Phase 2.4-D-pre → 3-5A: external 3D provider settings.
 *
 * Previously a pure reserved contract; now a real optional App Setting. The
 * provider itself is NOT yet implemented (offline skeleton), so the UI shows it
 * as configured/unavailable. `enabled` only marks user intent - it never makes
 * an implicit network call.
 */

/** Backward-compatible export: the external 3D provider default settings. */
export { DEFAULT_EXTERNAL3D_SETTINGS }

/** Whether the entry exists (always true this release). */
export function isExternal3DReserved(): boolean {
  return true
}

/** Human-readable notice shown in the settings UI. */
export function external3DReservedNotice(): string {
  return '外部 3D Provider：已预留配置（真实服务尚未实现）'
}

/** Why the entry is shown as unavailable/disabled. */
export function external3DDisabledReason(): string {
  return '真实外部 3D 服务尚未实现，仅可配置；当前版本继续使用本地 LocalLowPower / Mock。'
}

export { isBaseUrlFormatted }

/** Format-level validation result (no network). */
export interface External3DSettingsIssue {
  field: 'providerId' | 'baseUrl' | 'apiKey'
  message: string
}

export function validateExternal3DSettings(settings: ProviderEndpointSettings): External3DSettingsIssue[] {
  const issues: External3DSettingsIssue[] = []
  if (!settings.enabled) return issues
  if (!settings.providerId.trim()) {
    issues.push({ field: 'providerId', message: 'providerId 不能为空' })
  }
  if (!isBaseUrlFormatted(settings.baseUrl)) {
    issues.push({ field: 'baseUrl', message: 'baseUrl 必须是 http(s) 地址' })
  }
  if (!settings.apiKey) {
    issues.push({ field: 'apiKey', message: 'apiKey 不能为空（enabled 时必填）' })
  }
  return issues
}

export { providerStatus, redactApiKey }
