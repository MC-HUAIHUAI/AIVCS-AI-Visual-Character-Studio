import type { CharacterAsset, CharacterSpec, ViewConflict } from '@shared/types'
import type { ConfirmedSpecPatch } from './applyVisionResult'

/**
 * Pure multi-view review logic (no React/Zustand/network). Keeps the conflict
 * resolution and review composition rules deterministic and unit-testable.
 *
 * Core guarantees:
 * - unresolved / skipped conflicts are NEVER included in the suggestion set,
 *   therefore never written into the CharacterSpec;
 * - a resolved conflict replaces the resolver default with the chosen candidate;
 * - suggestions are the ONLY input to applyVisionResult.
 */

export type ReviewStatus = 'pending' | 'accepted' | 'modified' | 'rejected'

export interface VisionSuggestion {
  id: string
  field: string
  fieldLabel: string
  valueLabel: string
  confidence: number | null
  status: ReviewStatus
  patch: ConfirmedSpecPatch
}

export type ConflictDecision =
  | { kind: 'candidate'; index: number }
  | { kind: 'default' }
  | { kind: 'skip' }

export const PER_VIEW_MISSING_MESSAGE = '模型未提供逐视角分析'

const FIELD_LABELS: Record<string, string> = {
  characterType: '角色类型',
  species: '物种',
  bodyType: '体型',
  anatomy: '解剖特征',
  fur: '毛发',
  appearance: '外观配色',
  assetPatch: '外观资产',
  style: '风格',
  gender: '性别',
  heightCm: '身高',
  name: '角色名称',
  description: '描述',
  userNotes: '用户备注',
  visionAnalysis: '分析来源'
}

const ENUM_LABELS: Record<string, Record<string, string>> = {
  characterType: {
    human: '人类',
    'anime-human': '二次元人类',
    anthro: '兽人 / Furry',
    animal: '动物',
    'fantasy-creature': '奇幻生物',
    robot: '机器人',
    alien: '外星生物',
    custom: '自定义生物'
  },
  style: { stylized: '风格化', realistic: '写实', anime: '二次元', pixel: '像素' },
  gender: { female: '女', male: '男', neutral: '中性' },
  bodyType: {
    humanoid: '人类直立',
    'biped-anthro': '兽人直立',
    quadruped: '四足',
    bird: '鸟类',
    dragon: '龙形',
    custom: '自定义'
  },
  species: {
    wolf: '狼',
    fox: '狐',
    cat: '猫',
    dog: '狗',
    bear: '熊',
    rabbit: '兔',
    deer: '鹿',
    dragon: '龙',
    bird: '鸟',
    reptile: '爬行类',
    aquatic: '水生',
    insect: '昆虫',
    custom: '自定义'
  },
  fur: { none: '无', toon: 'Toon', anime: '动漫', stylized: '风格化', realistic: '写实' }
}

export function enumLabel(field: string, value: unknown): string {
  return typeof value === 'string' ? ENUM_LABELS[field]?.[value] ?? value : String(value ?? '')
}

function valueLabelOf(field: string, value: unknown): string {
  if (field === 'species' && value && typeof value === 'object') {
    const primary = (value as { primary?: string }).primary
    if (primary) return enumLabel('species', primary)
  }
  if (field === 'anatomy' && value && typeof value === 'object') {
    const flags = Object.entries(value as Record<string, unknown>).filter(([, v]) => v === true)
    return flags.length > 0 ? `${flags.length} 项特征` : '解剖结构'
  }
  if (field === 'fur' && value && typeof value === 'object') {
    const style = (value as { style?: string }).style
    return style ? `毛发：${enumLabel('fur', style)}` : '毛发'
  }
  if (field === 'appearance' && value && typeof value === 'object') {
    const palette = (value as { palette?: unknown[] }).palette
    if (Array.isArray(palette) && palette.length > 0) return `${palette.length} 种配色`
    const base = (value as { baseColor?: string }).baseColor
    return base ?? '外观'
  }
  if (field === 'assetPatch' && value && typeof value === 'object') {
    const patch = value as Record<string, unknown>
    const parts: string[] = []
    if (typeof patch.hairColor === 'string') parts.push(`发色 ${patch.hairColor}`)
    if (typeof patch.eyeColor === 'string') parts.push(`瞳色 ${patch.eyeColor}`)
    if (typeof patch.skinColor === 'string') parts.push(`肤色 ${patch.skinColor}`)
    if (Array.isArray(patch.outfitColors) && patch.outfitColors.length > 0)
      parts.push(`服装 ${patch.outfitColors.join('/')}`)
    if (typeof patch.backPattern === 'string') parts.push('背纹')
    return parts.length > 0 ? parts.join(' · ') : '外观资产'
  }
  if (field === 'heightCm' && typeof value === 'number') return `${value} cm`
  return typeof value === 'string' ? ENUM_LABELS[field]?.[value] ?? value : JSON.stringify(value) ?? '—'
}

/** Override a leaf path (e.g. "primary" or "ears") inside a cloned value. */
function setLeaf(base: unknown, leaf: string, value: unknown): unknown {
  if (leaf === '') return value
  const parts = leaf.split('.')
  const clone: Record<string, unknown> =
    base !== null && typeof base === 'object' && !Array.isArray(base)
      ? { ...(base as Record<string, unknown>) }
      : {}
  let cur = clone
  for (let i = 0; i < parts.length - 1; i++) {
    const seg = parts[i]
    const existing = cur[seg]
    const nextVal =
      existing !== null && typeof existing === 'object' && !Array.isArray(existing)
        ? { ...(existing as Record<string, unknown>) }
        : {}
    cur[seg] = nextVal
    cur = nextVal as Record<string, unknown>
  }
  cur[parts[parts.length - 1]] = value
  return clone
}

let idCounter = 0

function makeSuggestion(field: string, patch: ConfirmedSpecPatch, confidence: number): VisionSuggestion {
  const value = patch[field as keyof ConfirmedSpecPatch]
  return {
    id: `sug_${field}_${++idCounter}_${Date.now().toString(36)}`,
    field,
    fieldLabel: FIELD_LABELS[field] ?? field,
    valueLabel: valueLabelOf(field, value),
    confidence,
    status: 'pending',
    patch
  }
}

/**
 * Builds the review suggestion set from the unified specPatch.
 *
 * A top-level field covered by ANY conflict is:
 * - excluded entirely when any of its conflicts is unresolved or skipped
 *   (so acceptAll can never write it);
 * - included with the resolved candidate overriding the resolver default only
 *   when ALL its conflicts are resolved.
 */
export function buildReviewSuggestions(
  specPatch: Partial<CharacterSpec> & { assetPatch?: Partial<CharacterAsset> },
  conflicts: ViewConflict[],
  resolved: Record<string, number>,
  skipped: Record<string, boolean>,
  confidence: number
): VisionSuggestion[] {
  const suggestions: VisionSuggestion[] = []
  for (const key of Object.keys(specPatch) as (keyof ConfirmedSpecPatch)[]) {
    if (specPatch[key] === undefined) continue
    const covered = conflicts.filter((c) => c.field === key || c.field.startsWith(key + '.'))
    if (covered.length > 0) {
      const allResolved = covered.every((c) => resolved[c.field] !== undefined)
      const anySkipped = covered.some((c) => skipped[c.field])
      if (!allResolved || anySkipped) continue

      let patchValue: unknown = specPatch[key]
      for (const c of covered) {
        const idx = resolved[c.field]
        if (idx === undefined || idx < 0 || idx >= c.candidates.length) continue
        const leaf = c.field.slice(key.length + 1)
        patchValue = setLeaf(patchValue, leaf, c.candidates[idx].value)
      }
      suggestions.push(makeSuggestion(key, { [key]: patchValue } as ConfirmedSpecPatch, confidence))
    } else {
      suggestions.push(makeSuggestion(key, { [key]: specPatch[key] } as ConfirmedSpecPatch, confidence))
    }
  }
  return suggestions
}

/** Returns new {resolved, skipped} after applying a conflict decision. */
export function applyConflictDecision(
  conflicts: ViewConflict[],
  resolved: Record<string, number>,
  skipped: Record<string, boolean>,
  field: string,
  decision: ConflictDecision
): { resolved: Record<string, number>; skipped: Record<string, boolean> } {
  const nextResolved = { ...resolved }
  const nextSkipped = { ...skipped }
  const conflict = conflicts.find((c) => c.field === field)
  if (!conflict) return { resolved: nextResolved, skipped: nextSkipped }

  if (decision.kind === 'skip') {
    delete nextResolved[field]
    nextSkipped[field] = true
  } else if (decision.kind === 'candidate') {
    if (decision.index >= 0 && decision.index < conflict.candidates.length) {
      nextResolved[field] = decision.index
      delete nextSkipped[field]
    }
  } else {
    const rt = conflict.resolvedTo
    const idx = rt
      ? conflict.candidates.findIndex((c) => c.value === rt.value && c.view === rt.view)
      : -1
    nextResolved[field] = idx >= 0 ? idx : 0
    delete nextSkipped[field]
  }
  return { resolved: nextResolved, skipped: nextSkipped }
}

/**
 * UI-only warning for missing views. custom does not count toward
 * front/side/back completeness. Never modifies the CharacterSpec.
 */
export function missingViewWarning(views: Array<string | null | undefined>): string | null {
  const has = (v: string) => views.includes(v)
  if (has('front') && !has('side') && !has('back')) return '缺少侧面或背面参考图，多视角一致性有限'
  if (has('front') && has('side') && !has('back')) return '缺少背面参考图，多视角一致性有限'
  return null
}
