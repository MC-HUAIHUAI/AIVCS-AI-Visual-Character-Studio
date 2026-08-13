import { create } from 'zustand'
import type { VisionAnalysisResult, VisionImageInput } from '../core/providers/visionProvider'
import { getVisionProvider } from '../core/providers/visionRegistry'
import { applyVisionResult } from '../core/spec/applyVisionResult'
import type { ConfirmedSpecPatch } from '../core/spec/applyVisionResult'
import { useProjectStore } from './projectStore'

export type VisionStatus = 'idle' | 'analyzing' | 'success' | 'error'
export type SuggestionStatus = 'pending' | 'accepted' | 'modified' | 'rejected'

export interface VisionSuggestion {
  id: string
  field: string
  fieldLabel: string
  valueLabel: string
  confidence: number | null
  status: SuggestionStatus
  patch: ConfirmedSpecPatch
}

interface VisionState {
  status: VisionStatus
  providerId: string | null
  sourceImageIds: string[]
  result: VisionAnalysisResult | null
  suggestions: VisionSuggestion[]
  error: string | null
  progress: number

  analyze: (refs: VisionImageInput[], providerId: string) => Promise<void>
  acceptSuggestion: (id: string) => void
  rejectSuggestion: (id: string) => void
  acceptAll: () => void
  rejectAll: () => void
  reset: () => void
}

const FIELD_LABELS: Record<string, string> = {
  characterType: '角色类型',
  species: '物种',
  bodyType: '体型',
  anatomy: '解剖特征',
  fur: '毛发',
  appearance: '外观配色',
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

function labelOf(field: string, value: unknown): string {
  if (typeof value === 'string') {
    return ENUM_LABELS[field]?.[value] ?? value
  }
  if (field === 'heightCm' && typeof value === 'number') return `${value} cm`
  return JSON.stringify(value) ?? '—'
}

function suggestionForField(field: string, patch: ConfirmedSpecPatch, confidence: number): VisionSuggestion {
  let valueLabel = '—'
  if (field === 'species' && patch.species?.primary) valueLabel = labelOf('species', patch.species.primary)
  else if (field === 'anatomy' && patch.anatomy) {
    const flags = Object.entries(patch.anatomy)
      .filter(([, v]) => v === true)
      .map(([k]) => k)
    valueLabel = flags.length > 0 ? `${flags.length} 项特征` : '解剖结构'
  } else if (field === 'fur' && patch.fur) {
    valueLabel = patch.fur.style ? `毛发：${labelOf('fur', patch.fur.style)}` : '毛发'
  } else if (field === 'appearance' && patch.appearance) {
    const palette = patch.appearance.palette?.length ?? 0
    valueLabel = palette > 0 ? `${palette} 种配色` : patch.appearance.baseColor ?? '外观'
  } else {
    const raw = patch[field as keyof ConfirmedSpecPatch]
    valueLabel = labelOf(field, raw as unknown)
  }
  return {
    id: `sug_${field}_${Date.now().toString(36)}`,
    field,
    fieldLabel: FIELD_LABELS[field] ?? field,
    valueLabel,
    confidence,
    status: 'pending',
    patch: { [field]: patch[field as keyof ConfirmedSpecPatch] } as ConfirmedSpecPatch
  }
}

function buildSuggestions(result: VisionAnalysisResult): VisionSuggestion[] {
  const patch = result.specPatch as ConfirmedSpecPatch
  const fields = Object.keys(result.specPatch) as (keyof ConfirmedSpecPatch)[]
  return fields
    .filter((f) => patch[f] !== undefined)
    .map((f) => suggestionForField(f as string, patch, result.confidence))
}

export const useVisionStore = create<VisionState>((set, get) => ({
  status: 'idle',
  providerId: null,
  sourceImageIds: [],
  result: null,
  suggestions: [],
  error: null,
  progress: 0,

  analyze: async (refs, providerId) => {
    if (refs.length === 0) {
      set({ status: 'error', error: '请先选择一张参考图。' })
      return
    }
    const provider = getVisionProvider(providerId)
    set({
      status: 'analyzing',
      providerId,
      sourceImageIds: refs.map((r) => r.imageId),
      result: null,
      suggestions: [],
      error: null,
      progress: 0
    })
    try {
      const result = await provider.analyze(refs, (p) => set({ progress: p }))
      const suggestions = buildSuggestions(result)
      set({ status: 'success', result, suggestions, progress: 1 })
    } catch (err) {
      set({ status: 'error', error: err instanceof Error ? err.message : String(err), progress: 0 })
    }
  },

  acceptSuggestion: (id) => {
    const { suggestions, providerId, result, sourceImageIds } = get()
    const suggestion = suggestions.find((s) => s.id === id)
    if (!suggestion || suggestion.status !== 'pending') return

    const meta = {
      providerId: providerId ?? 'unknown',
      analyzedAt: new Date().toISOString(),
      sourceImageIds,
      confidence: result?.confidence ?? 0
    }
    const current = useProjectStore.getState().project.spec
    const safe = applyVisionResult(current, { ...suggestion.patch, visionAnalysis: meta })
    if (Object.keys(safe).length > 0) useProjectStore.getState().updateSpec(safe)

    set({
      suggestions: suggestions.map((s) => (s.id === id ? { ...s, status: 'accepted' as const } : s))
    })
  },

  rejectSuggestion: (id) => {
    set({
      suggestions: get().suggestions.map((s) =>
        s.id === id && s.status === 'pending' ? { ...s, status: 'rejected' as const } : s
      )
    })
  },

  acceptAll: () => {
    const pending = get().suggestions.filter((s) => s.status === 'pending')
    pending.forEach((s) => get().acceptSuggestion(s.id))
  },

  rejectAll: () => {
    set({
      suggestions: get().suggestions.map((s) =>
        s.status === 'pending' ? { ...s, status: 'rejected' as const } : s
      )
    })
  },

  reset: () =>
    set({
      status: 'idle',
      providerId: null,
      sourceImageIds: [],
      result: null,
      suggestions: [],
      error: null,
      progress: 0
    })
}))
