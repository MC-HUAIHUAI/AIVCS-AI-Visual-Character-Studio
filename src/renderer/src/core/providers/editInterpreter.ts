import type { CharacterEditCommand, CharacterSpec } from '@shared/types'
import { newId } from '../project/projectManager'

export interface EditInterpretation {
  command: CharacterEditCommand
  /** Human-readable message for the UI. */
  message: string
}

/**
 * Turns a natural-language edit request ("把尾巴变得更蓬松") into a structured
 * CharacterEditCommand. Real implementations would call an LLM; the mock uses
 * lightweight keyword matching so the pipeline is exercisable offline.
 */
export interface ICharacterEditInterpreter {
  readonly id: string
  readonly name: string
  interpret(input: string, spec: CharacterSpec): Promise<EditInterpretation>
}

interface Rule {
  keywords: string[]
  operation: string
  target: string
  params: (input: string) => Record<string, string>
}

function fluffy(input: string): Record<string, string> {
  return { fluffiness: /大|蓬松|浓/.test(input) ? '+30%' : '调整' }
}

const RULES: Rule[] = [
  { keywords: ['耳'], operation: 'modify_appendage', target: 'ears', params: () => ({ scale: '+20%' }) },
  { keywords: ['尾巴', '尾'], operation: 'modify_appendage', target: 'tail', params: fluffy },
  { keywords: ['鹿角'], operation: 'add_appendage', target: 'antlers', params: () => ({ count: '1 pair' }) },
  { keywords: ['角'], operation: 'add_appendage', target: 'horns', params: () => ({ count: '1 pair' }) },
  { keywords: ['翅膀', '翼'], operation: 'add_appendage', target: 'wings', params: () => ({}) },
  { keywords: ['风格', '画风', '写实', 'Kemono', '日系', '欧美'], operation: 'change_style', target: 'style', params: () => ({}) },
  { keywords: ['毛'], operation: 'modify_appearance', target: 'fur', params: (input) => ({ colors: input.includes('渐变') ? 'gradient' : 'edit' }) },
  { keywords: ['身体', '比例', '体型'], operation: 'modify_anatomy', target: 'proportions', params: () => ({}) },
  { keywords: ['颜色', '配色', '白', '黑', '蓝', '红', '橙'], operation: 'modify_appearance', target: 'colors', params: (input) => ({ palette: input }) }
]

const FALLBACK = { operation: 'modify_appearance', target: 'general' }

/**
 * Mock interpreter. Records the structured command and reports it; it does not
 * actually modify the 3D model (that is real-AI work for a later phase).
 */
export class MockEditInterpreter implements ICharacterEditInterpreter {
  readonly id = 'mock-edit'
  readonly name = 'Mock（本地）'

  async interpret(input: string, _spec: CharacterSpec): Promise<EditInterpretation> {
    const rule = RULES.find((r) => r.keywords.some((k) => input.includes(k))) ?? null
    const command: CharacterEditCommand = {
      id: newId(),
      operation: rule?.operation ?? FALLBACK.operation,
      target: rule?.target ?? FALLBACK.target,
      parameters: rule ? rule.params(input) : { note: input },
      rawInput: input,
      createdAt: new Date().toISOString()
    }
    const opLabel: Record<string, string> = {
      modify_appendage: '修改部件',
      add_appendage: '添加部件',
      change_style: '更改风格',
      modify_anatomy: '修改结构',
      modify_appearance: '修改外观'
    }
    return {
      command,
      message: `（Mock）已解析编辑意图：${opLabel[command.operation] ?? command.operation} → ${command.target}。尚未实际修改模型。`
    }
  }
}

export const editInterpreters: ICharacterEditInterpreter[] = [new MockEditInterpreter()]
