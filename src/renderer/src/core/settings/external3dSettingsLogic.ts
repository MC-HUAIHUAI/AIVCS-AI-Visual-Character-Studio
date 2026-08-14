import type { External3DProviderSettings } from '@shared/types'

/**
 * Phase 2.4-D-pre: reserved external 3D provider settings contract.
 *
 * PURE logic only - no network, no fetch, no provider calls. Even when
 * `enabled` is true this version must never trigger any request; `enabled` is
 * purely a future config contract. `baseUrl` is only ever string/format
 * checked (never HEAD/GET/ping validated).
 */

export const DEFAULT_EXTERNAL3D_SETTINGS: External3DProviderSettings = {
  enabled: false,
  providerId: '',
  baseUrl: ''
}

/** Whether the reserved external provider entry is wired in this release. */
export function isExternal3DReserved(): boolean {
  return true
}

/** Human-readable reserved-state notice shown in the settings UI. */
export function external3DReservedNotice(): string {
  return '预留接口，当前版本未启用'
}

/** Why the UI shows the entry as reserved (always the same in this release). */
export function external3DDisabledReason(): string {
  return external3DReservedNotice()
}

/** Format-level check only - never contacts the address. */
export function isBaseUrlFormatted(value: string): boolean {
  if (!value) return false
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

/** Format-level validation result (no network). */
export interface External3DSettingsIssue {
  field: 'providerId' | 'baseUrl'
  message: string
}

export function validateExternal3DSettings(settings: External3DProviderSettings): External3DSettingsIssue[] {
  const issues: External3DSettingsIssue[] = []
  if (!settings.enabled) return issues
  if (settings.providerId.trim() === '') {
    issues.push({ field: 'providerId', message: 'providerId 不能为空' })
  }
  if (!isBaseUrlFormatted(settings.baseUrl)) {
    issues.push({ field: 'baseUrl', message: 'baseUrl 必须是 http(s) 地址' })
  }
  return issues
}
