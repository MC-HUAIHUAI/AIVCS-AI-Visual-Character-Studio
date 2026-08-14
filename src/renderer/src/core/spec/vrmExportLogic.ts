import type { ModelAsset } from '@shared/types'

/**
 * Phase 2.7-D: frontend VRM export logic.
 *
 * PURE logic only - no network, no fetch. The actual VRM bytes are fetched from
 * the project's local backend (GET /api/v1/models/{id}/vrm) by httpProvider.
 *
 * `body_type` is ALWAYS passed through verbatim from CharacterSpec.bodyType -
 * this module never guesses or converts body types; the backend whitelist is
 * the single source of truth (humanoid / biped-anthro / custom export;
 * quadruped / bird / dragon -> 400).
 */

/** Backend provider ids that produce a persisted ModelRecord on the backend. */
const BACKEND_PROVIDER_IDS: ReadonlySet<string> = new Set([
  'backend-fastapi',
  'backend-local-lowpower',
  'backend-mock-remote'
])

/** Body types the backend accepts (mirrors VRM_SUPPORTED_BODY_TYPES). */
export const VRM_EXPORTABLE_BODY_TYPES: ReadonlySet<string> = new Set([
  'humanoid',
  'biped-anthro',
  'custom'
])

export function isBackendModel(model: ModelAsset | null | undefined): boolean {
  if (!model) return false
  if (model.source !== 'generated') return false
  return model.providerId ? BACKEND_PROVIDER_IDS.has(model.providerId) : false
}

/**
 * Whether the VRM export button should be available.
 *
 * Requires a backend-persisted model (demo / local mock models have no backend
 * ModelRecord and can never be exported) plus a reachable backend. When the
 * model's analyzer stats explicitly say `skinned === false` the button is
 * disabled (no skinned GLB). A missing `skinned` (old project / old stats) is
 * treated as unknown and allowed - the backend is then the source of truth and
 * its 400 surfaces through vrmErrorText. VRM availability is never faked.
 */
export function canExportVrm(
  model: ModelAsset | null | undefined,
  backendOnline: boolean
): boolean {
  if (!backendOnline || !isBackendModel(model)) return false
  if (model?.glbStats?.skinned === false) return false
  return true
}

/** Sanitizes a name into a safe file name. */
export function sanitizeFileName(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim()
}

/** Builds the default save file name, e.g. "角色名.vrm". */
export function vrmFileName(specName: string): string {
  return `${sanitizeFileName(specName) || 'AIVCS Character'}.vrm`
}

export interface VrmErrorInfo {
  message: string
}

/**
 * Maps a VRM export failure to a user-understandable message.
 * `status` is the HTTP status; `detail` is the backend's error body (FastAPI
 * detail string); `isNetwork` marks local backend unreachable failures.
 */
export function vrmErrorText(
  status: number | null,
  detail: string | null,
  isNetwork: boolean
): string {
  if (isNetwork || status === null) {
    return '后端离线，无法导出 VRM。请先运行 `npm run backend`。'
  }
  if (status === 404) {
    return detail?.trim() ? detail : '模型不存在（可能已过期），无法导出 VRM。'
  }
  if (status === 400) {
    return detail?.trim() ? detail : '该模型无法导出 VRM（后端拒绝了请求）。'
  }
  return `导出 VRM 失败（HTTP ${status}）。`
}

/** Sanitized .vrm file name for the save dialog default. */
export function vrmExportDefaultName(specName: string): string {
  return vrmFileName(specName)
}
