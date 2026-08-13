import type { AIImage3DProvider, GeneratedModelResult, GenerationProgress } from './aiProvider'
import type { GenerationAbortSignal } from './aiProvider'
import type { BodyType, CharacterSpec, RigProfileId } from '@shared/types'
import type { VisionImageInput } from './visionProvider'
import { demoUrlForType, fetchBytes, isNonHuman } from '../demo/demoCharacter'
import { getRigProfile } from '@shared/types'

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

const CHARACTER_TYPE_LABEL: Record<string, string> = {
  human: '人类',
  'anime-human': '二次元人类',
  anthro: '兽人 / Furry',
  animal: '动物',
  'fantasy-creature': '奇幻生物',
  robot: '机器人',
  alien: '外星生物',
  custom: '自定义生物'
}

const RIG_FOR_BODY_TYPE: Record<BodyType, RigProfileId> = {
  humanoid: 'humanoid',
  'biped-anthro': 'anthropomorphic',
  quadruped: 'quadruped',
  bird: 'bird',
  dragon: 'dragon',
  custom: 'custom'
}

function buildSteps(spec: CharacterSpec): string[] {
  const steps: string[] = ['解析角色规格（' + (CHARACTER_TYPE_LABEL[spec.characterType] ?? spec.characterType) + '）']
  if (isNonHuman(spec.characterType)) {
    steps.push('识别物种与解剖结构（模拟）')
  }
  steps.push('生成 3D 拓扑（模拟）')
  steps.push('应用材质与贴图（模拟）')
  if (spec.fur?.enabled) {
    const furLabel: Record<string, string> = {
      toon: 'Toon 毛发',
      anime: '动漫毛发',
      stylized: '风格化毛发',
      realistic: '写实毛发'
    }
    steps.push(`应用${furLabel[spec.fur.style] ?? '毛发'}（模拟）`)
  }
  steps.push(`按「${getRigProfile(RIG_FOR_BODY_TYPE[spec.bodyType ?? 'humanoid']).label}」RigProfile 生成骨骼（模拟）`)
  steps.push('导出 GLB')
  return steps
}

/**
 * Fully local mock provider. Replays the image-to-3D pipeline with simulated
 * progress and returns a demo GLB matching the character's type (human chibi vs
 * anthro fox). Requires no network and no AI API.
 */
export class MockImage3DProvider implements AIImage3DProvider {
  readonly id = 'mock-local'
  readonly name = 'Mock（本地）'
  readonly description =
    '本地模拟 image-to-3D 流程并按角色类型返回演示模型（人类 / 兽人狐），无需任何 AI API。'
  readonly requiresBackend = false
  readonly capabilities = {
    mode: 'local' as const,
    gpuRequired: false,
    maxReferences: 0,
    outputFormat: 'glb' as const,
    supportsCancel: true,
    supportsTimeout: false,
    backendId: 'mock'
  }

  async generate(
    spec: CharacterSpec,
    references: VisionImageInput[],
    onProgress: (p: GenerationProgress) => void,
    signal?: GenerationAbortSignal
  ): Promise<GeneratedModelResult> {
    const steps = buildSteps(spec)
    const total = steps.length

    for (let i = 0; i < total; i++) {
      if (signal?.aborted) throw new Error('generation aborted')
      let message = steps[i]
      if (steps[i].includes('物种') && spec.species?.confidence == null && references.length === 0) {
        message = '无法确定角色物种，请选择或补充参考图。继续使用当前设定生成。'
      }
      onProgress({ step: i, totalSteps: total, percent: i / total, message })
      await sleep(i === 2 ? 900 : 380)
    }
    if (signal?.aborted) throw new Error('generation aborted')
    onProgress({ step: total, totalSteps: total, percent: 1, message: '生成完成' })

    const bytes = await fetchBytes(demoUrlForType(spec.characterType))

    return {
      modelId: `model_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
      name: spec.characterType === 'human' || spec.characterType === 'anime-human' ? 'generated_character' : 'generated_creature',
      format: 'glb',
      sizeBytes: bytes.byteLength,
      providerId: this.id,
      sourceJobId: `mock_${Date.now().toString(36)}`,
      mime: 'model/gltf-binary',
      bytes
    }
  }
}
