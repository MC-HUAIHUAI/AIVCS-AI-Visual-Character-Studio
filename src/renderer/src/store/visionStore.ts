import { create } from 'zustand'
import type { ViewAnalysis, ViewConflict } from '@shared/types'
import type { VisionAnalysisResult, VisionImageInput } from '../core/providers/visionProvider'
import { getVisionProvider } from '../core/providers/visionRegistry'
import { applyVisionResult } from '../core/spec/applyVisionResult'
import {
  applyConflictDecision,
  buildReviewSuggestions
} from '../core/spec/visionReviewLogic'
import type { VisionSuggestion } from '../core/spec/visionReviewLogic'
import { useProjectStore } from './projectStore'

export type VisionStatus = 'idle' | 'analyzing' | 'success' | 'error'
export type SuggestionStatus = VisionSuggestion['status']

interface VisionState {
  status: VisionStatus
  providerId: string | null
  sourceImageIds: string[]
  result: VisionAnalysisResult | null
  viewAnalyses: ViewAnalysis[]
  conflicts: ViewConflict[]
  resolved: Record<string, number>
  skipped: Record<string, boolean>
  suggestions: VisionSuggestion[]
  error: string | null
  progress: number

  analyze: (refs: VisionImageInput[], providerId: string) => Promise<void>
  acceptSuggestion: (id: string) => void
  rejectSuggestion: (id: string) => void
  acceptAll: () => void
  rejectAll: () => void
  resolveConflict: (field: string, candidateIndex: number) => void
  resolveConflictDefault: (field: string) => void
  skipConflict: (field: string) => void
  reset: () => void
}

function rebuildSuggestions(
  result: VisionAnalysisResult,
  resolved: Record<string, number>,
  skipped: Record<string, boolean>
): VisionSuggestion[] {
  return buildReviewSuggestions(result.specPatch, result.conflicts ?? [], resolved, skipped, result.confidence)
}

export const useVisionStore = create<VisionState>((set, get) => ({
  status: 'idle',
  providerId: null,
  sourceImageIds: [],
  result: null,
  viewAnalyses: [],
  conflicts: [],
  resolved: {},
  skipped: {},
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
      viewAnalyses: [],
      conflicts: [],
      resolved: {},
      skipped: {},
      suggestions: [],
      error: null,
      progress: 0
    })
    try {
      const result = await provider.analyze(refs, (p) => set({ progress: p }))
      set({
        status: 'success',
        result,
        viewAnalyses: result.perView ?? [],
        conflicts: result.conflicts ?? [],
        progress: 1,
        suggestions: rebuildSuggestions(result, {}, {})
      })
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

    // Phase 3-2: a confirmed assetPatch lands in the CharacterAsset (derived
    // renderable appearance) - it is NOT a CharacterSpec field.
    if (suggestion.patch.assetPatch) {
      useProjectStore.getState().applyCharacterAssetPatch(suggestion.patch.assetPatch)
    }

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
    // Unresolved/skipped conflicts are never in the suggestion set, so acceptAll
    // can only ever write unifiedPatch + resolved overrides - and always through
    // applyVisionResult.
    pending.forEach((s) => get().acceptSuggestion(s.id))
  },

  rejectAll: () => {
    set({
      suggestions: get().suggestions.map((s) =>
        s.status === 'pending' ? { ...s, status: 'rejected' as const } : s
      )
    })
  },

  resolveConflict: (field, candidateIndex) => {
    const { conflicts, resolved, skipped, result } = get()
    if (!result) return
    const next = applyConflictDecision(conflicts, resolved, skipped, field, { kind: 'candidate', index: candidateIndex })
    set({
      resolved: next.resolved,
      skipped: next.skipped,
      suggestions: rebuildSuggestions(result, next.resolved, next.skipped)
    })
  },

  resolveConflictDefault: (field) => {
    const { conflicts, resolved, skipped, result } = get()
    if (!result) return
    const next = applyConflictDecision(conflicts, resolved, skipped, field, { kind: 'default' })
    set({
      resolved: next.resolved,
      skipped: next.skipped,
      suggestions: rebuildSuggestions(result, next.resolved, next.skipped)
    })
  },

  skipConflict: (field) => {
    const { conflicts, resolved, skipped, result } = get()
    if (!result) return
    const next = applyConflictDecision(conflicts, resolved, skipped, field, { kind: 'skip' })
    set({
      resolved: next.resolved,
      skipped: next.skipped,
      suggestions: rebuildSuggestions(result, next.resolved, next.skipped)
    })
  },

  reset: () =>
    set({
      status: 'idle',
      providerId: null,
      sourceImageIds: [],
      result: null,
      viewAnalyses: [],
      conflicts: [],
      resolved: {},
      skipped: {},
      suggestions: [],
      error: null,
      progress: 0
    })
}))
