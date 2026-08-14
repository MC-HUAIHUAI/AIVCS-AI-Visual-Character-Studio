import type { GlbStats } from '@shared/types'

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
}

export interface InfoRow {
  label: string
  value: string | null
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
 */
export function buildModelInfoRows(model: ModelInfoModel): ModelInfoOutput {
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
