import { create } from 'zustand'
import type { CharacterSpec, GenerationJob, ImageAsset, ModelFormat } from '@shared/types'
import type { AIImage3DProvider, GenerationAbortSignal } from '../core/providers/aiProvider'
import { getProvider } from '../core/providers/registry'
import {
  cancelGenerationJob,
  createGenerationJob,
  downloadModel,
  pollGenerationJob
} from '../core/providers/httpProvider'
import {
  applyDtoToJob,
  buildGenerationRequest,
  canRetry,
  createQueuedJob,
  isTerminal,
  modelAssetFromResult,
  referencesWithinLimit,
  retryJobFrom,
  safeErrorMessage
} from '../core/spec/generationLogic'
import type { GenerationRequest, JobDto } from '../core/spec/generationLogic'
import { useProjectStore } from './projectStore'
import { newId } from '../core/project/projectManager'

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

interface RunContext {
  request: GenerationRequest
  providerId: string
  signal: GenerationAbortSignal
  backendJobId?: string
}

interface GenerationState {
  jobs: Record<string, GenerationJob>
  activeJobId: string | null
  contexts: Record<string, RunContext>

  runGeneration: (spec: CharacterSpec, references: ImageAsset[], providerId: string, timeoutSeconds?: number) => Promise<void>
  cancelJob: (jobId: string) => boolean
  retryJob: (jobId: string) => boolean
  clearFinished: () => void
}

function updateJob(
  jobs: Record<string, GenerationJob>,
  jobId: string,
  patch: Partial<GenerationJob>
): Record<string, GenerationJob> {
  const prev = jobs[jobId]
  if (!prev) return jobs
  return { ...jobs, [jobId]: { ...prev, ...patch } }
}

export const useGenerationStore = create<GenerationState>((set, get) => ({
  jobs: {},
  activeJobId: null,
  contexts: {},

  runGeneration: async (spec, references, providerId, timeoutSeconds) => {
    const provider = getProvider(providerId)
    const request = buildGenerationRequest(spec, references, timeoutSeconds)
    const context: RunContext = { request, providerId, signal: { aborted: false } }

    if (!referencesWithinLimit(references)) {
      const job = createQueuedJob(newId(), provider.name)
      set((s) => ({
        jobs: {
          ...s.jobs,
          [job.id]: {
            ...job,
            status: 'failed',
            error: '最多 4 张参考图',
            message: '最多 4 张参考图',
            retryable: false
          }
        },
        contexts: { ...s.contexts, [job.id]: context },
        activeJobId: job.id
      }))
      return
    }

    const job = createQueuedJob(newId(), provider.name)
    set((s) => ({
      jobs: { ...s.jobs, [job.id]: job },
      contexts: { ...s.contexts, [job.id]: context },
      activeJobId: job.id
    }))

    await runFlow(job.id, provider, context)
  },

  cancelJob: (jobId) => {
    const { jobs, contexts } = get()
    const job = jobs[jobId]
    const context = contexts[jobId]
    if (!job || !context) return false
    if (isTerminal(job.status) || context.signal.aborted) return false
    context.signal.aborted = true
    return true
  },

  retryJob: (jobId) => {
    const { jobs, contexts } = get()
    const prev = jobs[jobId]
    const context = contexts[jobId]
    if (!prev || !context || !canRetry(prev.status)) return false

    // A retry is a BRAND NEW job with a new id; the old job stays for history.
    const retry = retryJobFrom(prev, newId())
    const newContext: RunContext = { request: context.request, providerId: context.providerId, signal: { aborted: false } }
    set((s) => ({
      jobs: { ...s.jobs, [retry.id]: retry },
      contexts: { ...s.contexts, [retry.id]: newContext },
      activeJobId: retry.id
    }))
    void runFlow(retry.id, getProvider(context.providerId), newContext)
    return true
  },

  clearFinished: () => {
    const { jobs, contexts } = get()
    const running = Object.fromEntries(Object.entries(jobs).filter(([, j]) => !isTerminal(j.status)))
    const keepCtx = Object.fromEntries(
      Object.entries(contexts).filter(([id]) => Object.prototype.hasOwnProperty.call(running, id))
    )
    set({ jobs: running, contexts: keepCtx })
  }
}))

async function runFlow(jobId: string, provider: AIImage3DProvider, context: RunContext): Promise<void> {
  const finish = (patch: Partial<GenerationJob>): void => {
    useGenerationStore.setState((s) => ({
      activeJobId: s.activeJobId === jobId ? null : s.activeJobId,
      jobs: updateJob(s.jobs, jobId, { ...patch, finishedAt: new Date().toISOString() })
    }))
  }
  const progress = (patch: Partial<GenerationJob>): void => {
    useGenerationStore.setState((s) => ({ jobs: updateJob(s.jobs, jobId, patch) }))
  }
  const read = (): GenerationJob => useGenerationStore.getState().jobs[jobId]

  if (provider.requiresBackend) {
    await backendFlow(context, provider.capabilities.backendId, progress, finish, read)
  } else {
    await localFlow(provider, context, progress, finish)
  }
}

async function backendFlow(
  context: RunContext,
  backendProviderId: string,
  progress: (patch: Partial<GenerationJob>) => void,
  finish: (patch: Partial<GenerationJob>) => void,
  read: () => GenerationJob
): Promise<void> {
  try {
    const created = await createGenerationJob({
      backendProviderId,
      spec: context.request.spec,
      references: context.request.references,
      timeoutSeconds: context.request.timeoutSeconds
    })
    context.backendJobId = created.jobId

    let dto: JobDto | null = null
    for (;;) {
      if (context.signal.aborted) {
        // Single cancel send, guarded by the abort flag.
        try {
          await cancelGenerationJob(context.backendJobId)
        } catch {
          // safe: backend may already be terminal
        }
        try {
          dto = await pollGenerationJob(context.backendJobId)
        } catch {
          dto = null
        }
        if (dto && isTerminal(dto.status)) {
          finish(applyDtoToJob(read(), dto))
        } else {
          finish({ status: 'cancelled', cancelledByUser: true, message: '已取消' })
        }
        return
      }

      dto = await pollGenerationJob(context.backendJobId)
      progress(applyDtoToJob(read(), dto))
      if (isTerminal(dto.status)) break
      await sleep(450)
    }

    if (dto && dto.status === 'done' && dto.result?.model_id) {
      const { bytes } = await downloadModel(dto.result.model_id)
      const model = modelAssetFromResult(dto.result.model_id, 'generated_character', {
        format: dto.result.format as ModelFormat | undefined,
        mime: dto.result.mime,
        sizeBytes: dto.result.size_bytes,
        providerId: dto.result.provider_id,
        sourceJobId: dto.result.source_job_id,
        glbStats: dto.result.stats
      })
      useProjectStore.getState().addModel(model, bytes)
      finish({ status: 'done', progress: 100, message: '生成完成', resultModelId: dto.result.model_id })
      return
    }
    if (dto && dto.status !== 'done') {
      finish({ status: dto.status, error: dto.error, message: dto.error ?? '生成失败' })
      return
    }
    finish({ status: 'failed', retryable: true, error: '生成失败', message: '生成失败' })
  } catch (err) {
    if (context.signal.aborted) {
      finish({ status: 'cancelled', cancelledByUser: true, message: '已取消' })
    } else {
      const msg = safeErrorMessage(err)
      finish({ status: 'failed', retryable: true, error: msg, message: msg })
    }
  }
}

async function localFlow(
  provider: AIImage3DProvider,
  context: RunContext,
  progress: (patch: Partial<GenerationJob>) => void,
  finish: (patch: Partial<GenerationJob>) => void
): Promise<void> {
  progress({ status: 'running', message: '开始生成…' })
  const labels: string[] = []
  try {
    const result = await provider.generate(context.request.spec, context.request.references, (p) => {
      while (labels.length < p.totalSteps) labels.push(`Step ${labels.length + 1}`)
      if (p.step < labels.length) labels[p.step] = p.message
      progress({
        status: 'running',
        progress: Math.round(p.percent * 100),
        message: p.message,
        steps: labels.map((label, i) => ({
          index: i,
          label,
          status: i < p.step ? 'done' : i === p.step ? 'running' : 'pending'
        }))
      })
    }, context.signal)

    const model = modelAssetFromResult(result.modelId, result.name, {
      format: result.format,
      mime: result.mime,
      sizeBytes: result.sizeBytes,
      providerId: result.providerId,
      sourceJobId: result.sourceJobId,
      glbStats: result.glbStats
    })
    useProjectStore.getState().addModel(model, result.bytes)
    finish({ status: 'done', progress: 100, message: '生成完成', resultModelId: result.modelId })
  } catch (err) {
    if (context.signal.aborted) {
      finish({ status: 'cancelled', cancelledByUser: true, message: '已取消' })
    } else {
      const msg = safeErrorMessage(err)
      finish({ status: 'failed', retryable: true, error: msg, message: msg })
    }
  }
}
