import { create } from 'zustand'
import type { CharacterSpec, GenerationJob, GenerationJobStep, ImageAsset } from '@shared/types'
import type { AIImage3DProvider } from '../core/providers/aiProvider'
import { getProvider } from '../core/providers/registry'
import { useProjectStore } from './projectStore'
import { newId } from '../core/project/projectManager'

interface GenerationState {
  jobs: Record<string, GenerationJob>
  activeJobId: string | null
  runGeneration: (spec: CharacterSpec, references: ImageAsset[], providerId: string) => Promise<void>
  clearFinished: () => void
}

function buildSteps(labels: string[], stepIndex: number, total: number): GenerationJobStep[] {
  const steps: GenerationJobStep[] = []
  for (let i = 0; i < total; i++) {
    steps.push({
      index: i,
      label: labels[i] ?? `Step ${i + 1}`,
      status: i < stepIndex ? 'done' : i === stepIndex ? 'running' : 'pending'
    })
  }
  return steps
}

export const useGenerationStore = create<GenerationState>((set, get) => ({
  jobs: {},
  activeJobId: null,

  runGeneration: async (spec, references, providerId) => {
    const provider: AIImage3DProvider = getProvider(providerId)
    const jobId = newId()
    const now = new Date().toISOString()
    const job: GenerationJob = {
      id: jobId,
      provider: provider.name,
      status: 'running',
      progress: 0,
      message: '正在开始生成…',
      steps: [],
      createdAt: now,
      finishedAt: null,
      error: null,
      resultModelId: null
    }

    set((s) => ({ jobs: { ...s.jobs, [jobId]: job }, activeJobId: jobId }))

    const updateJob = (patch: Partial<GenerationJob>): void => {
      set((s) => {
        const prev = s.jobs[jobId]
        if (!prev) return s
        return { jobs: { ...s.jobs, [jobId]: { ...prev, ...patch } } }
      })
    }

    try {
      const labels: string[] = []
      const result = await provider.generate(spec, references, (p) => {
        if (labels.length < p.totalSteps) {
          while (labels.length < p.totalSteps) labels.push(`Step ${labels.length + 1}`)
        }
        if (p.step < labels.length) labels[p.step] = p.message
        updateJob({
          progress: Math.round(p.percent * 100),
          message: p.message,
          steps: buildSteps(labels, p.step, p.totalSteps)
        })
      })

      const modelId = newId()
      updateJob({ progress: 100, message: '生成完成', status: 'done', resultModelId: modelId })

      useProjectStore.getState().addModel(
        {
          id: modelId,
          name: result.name,
          source: 'generated',
          format: result.format,
          filePath: result.filePath ?? null,
          addedAt: new Date().toISOString()
        },
        result.bytes
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      updateJob({ status: 'failed', error: message, message })
    } finally {
      set((s) => ({
        activeJobId: s.activeJobId === jobId ? null : s.activeJobId,
        jobs: {
          ...s.jobs,
          [jobId]: { ...s.jobs[jobId], finishedAt: new Date().toISOString() }
        }
      }))
    }
  },

  clearFinished: () => {
    const { jobs } = get()
    const next = Object.fromEntries(Object.entries(jobs).filter(([, j]) => j.status === 'running'))
    set({ jobs: next })
  }
}))
