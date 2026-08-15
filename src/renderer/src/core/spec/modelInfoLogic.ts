import type { GlbStats, ModelTextureMeta } from '@shared/types'

/**
 * Pure model-info formatting/mapping (Phase 2.5-C). No React/Zustand/network.
 *
 * Semantics:
 *  - glbStats.dimensions/bounds are the GLB ANALYZER's LOCAL (accessor) space;
 *  - the viewport Box3 dims are the WORLD/scene space after loading;
 *  - these two are intentionally kept separate and never mixed.
 */

export interface ModelInfoModel {
  glbStats?: GlbStats
  sizeBytes?: number
  normalizations?: string[]
  /** Phase 3-J: texture/paint output metadata (absent/null = shape-only). */
  texture?: ModelTextureMeta | null
  /** Phase 3-J: model format (glb/vrm) for VRM status. */
  format?: string
}

export interface InfoRow {
  label: string
  value: string | null
}

export type VrmModelState = 'bound' | 'bindable' | 'unsupported' | 'unbound'

/** Body types that can be bound to a VRM 1.0 humanoid by the local rigger. */
const VRM_BINDABLE_BODY_TYPES = ['humanoid', 'biped-anthro', 'custom']

/** True when the spec body type can be rigged to VRM (humanoid-like). */
export function canConvertToVrm(bodyType: string | null | undefined): boolean {
  return VRM_BINDABLE_BODY_TYPES.includes((bodyType ?? '').trim().toLowerCase())
}

/** VRM workflow status for a model (data-driven; never guesses the rig). */
export function vrmStatusForModel(
  model: ModelInfoModel,
  opts: { hasDerivedVrm: boolean; bodyType: string | null | undefined }
): { state: VrmModelState; label: string } {
  if (model.format === 'vrm') return { state: 'bound', label: '已绑定（VRM 1.0）' }
  if (opts.hasDerivedVrm) return { state: 'bound', label: '已转换 VRM' }
  const bt = (opts.bodyType ?? '').trim().toLowerCase()
  if (!bt) return { state: 'unbound', label: '未绑定' }
  if (canConvertToVrm(bt)) return { state: 'bindable', label: '未绑定（可转换为 VRM）' }
  return { state: 'unsupported', label: '不支持 VRM 骨骼绑定（非人体）' }
}

/** Human-readable texture status (shape-only default; never claims texture). */
export function textureStatusLabel(model: ModelInfoModel): string | null {
  const t = model.texture
  if (!t || !t.supported) return '无纹理（shape-only）'
  const parts: string[] = []
  if (t.maps.baseColor) parts.push('BaseColor')
  if (t.maps.normal) parts.push('Normal')
  if (t.maps.metallicRoughness) parts.push('MetallicRoughness')
  if (parts.length === 0) return '有纹理'
  return parts.join(' + ')
}

export interface ModelInfoOutput {
  rows: InfoRow[]
  warnings: string[]
  normalizations: string[]
}

export function formatBytes(bytes: number | undefined): string | null {
  if (bytes === undefined || bytes === null || Number.isNaN(bytes)) return null
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export function formatDimensions(d: { x: number; y: number; z: number }): string {
  return `${d.x.toFixed(2)} × ${d.y.toFixed(2)} × ${d.z.toFixed(2)} m`
}

export function formatVec3(arr: number[] | undefined): string | null {
  if (!Array.isArray(arr) || arr.length < 3) return null
  return `(${arr.slice(0, 3).map((v) => v.toFixed(3)).join(', ')})`
}

/**
 * Builds display rows from a ModelAsset (glbStats optional). Missing fields get
 * value null so the UI renders "—"; nothing is guessed or recomputed.
 *
 * `opts.vrm` is the VRM workflow context (has a derived VRM? + spec body type)
 * used only for the VRM status row - never claimed when unknown.
 */
export function buildModelInfoRows(
  model: ModelInfoModel,
  opts: { hasDerivedVrm?: boolean; bodyType?: string | null | undefined } = {}
): ModelInfoOutput {
  const s = model.glbStats
  const rows: InfoRow[] = []
  const put = (label: string, value: string | null): void => {
    rows.push({ label, value })
  }

  put('文件大小', formatBytes(model.sizeBytes ?? s?.sizeBytes))
  put('GLB 版本', s ? `glTF ${s.version}` : null)
  put('网格数', s ? String(s.meshCount) : null)
  put('Primitive 数', s ? String(s.primitiveCount) : null)
  put('顶点数', s ? String(s.vertexCount) : null)
  put('索引数', s ? String(s.indexCount) : null)
  put('三角形数', s ? String(s.triangleCount) : null)
  put('材质数', s ? String(s.materialCount) : null)
  put('贴图数', s ? String(s.textureCount) : null)
  put('骨骼状态', s ? (s.skinned == null ? null : s.skinned ? '有骨骼（skinned）' : '无骨骼（静态网格）') : null)
  put('纹理状态', textureStatusLabel(model))
  put('VRM 状态', vrmStatusForModel(model, { hasDerivedVrm: opts.hasDerivedVrm ?? false, bodyType: opts.bodyType }).label)
  put('法线', s ? (s.hasNormals ? '有' : '无') : null)
  put('UV', s ? (s.hasUVs ? '有' : '无') : null)
  put('GLB 分析尺寸（局部坐标）', s?.dimensions ? formatDimensions(s.dimensions) : null)
  put('Bounds min', s?.bounds ? formatVec3(s.bounds.min) : null)
  put('Bounds max', s?.bounds ? formatVec3(s.bounds.max) : null)

  return {
    rows,
    warnings: s?.warnings ?? [],
    normalizations: model.normalizations ?? []
  }
}
