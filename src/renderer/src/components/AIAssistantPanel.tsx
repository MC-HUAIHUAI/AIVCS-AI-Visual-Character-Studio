import { useEffect, useMemo, useState } from 'react'
import { useProjectStore } from '../store/projectStore'
import { useGenerationStore } from '../store/generationStore'
import { useUIStore } from '../store/uiStore'
import { providers } from '../core/providers/registry'
import { editInterpreters } from '../core/providers/editInterpreter'
import { getRigProfile, RIG_PROFILES } from '@shared/types'
import VisionAnalysisPanel from './VisionAnalysisPanel'
import type {
  AnatomyGraph,
  BodyType,
  CharacterStyle,
  CharacterGender,
  CharacterType,
  FurStyle,
  SpeciesKind,
  TailMode
} from '@shared/types'

const CHARACTER_TYPES: { id: CharacterType; label: string }[] = [
  { id: 'human', label: '人类' },
  { id: 'anime-human', label: '二次元人类' },
  { id: 'anthro', label: '兽人 / Furry' },
  { id: 'animal', label: '动物' },
  { id: 'fantasy-creature', label: '奇幻生物' },
  { id: 'robot', label: '机器人' },
  { id: 'alien', label: '外星生物' },
  { id: 'custom', label: '自定义生物' }
]

const STYLES: { id: CharacterStyle; label: string }[] = [
  { id: 'stylized', label: '风格化' },
  { id: 'realistic', label: '写实' },
  { id: 'anime', label: '二次元' },
  { id: 'pixel', label: '像素' }
]

const GENDERS: { id: CharacterGender; label: string }[] = [
  { id: 'female', label: '女' },
  { id: 'male', label: '男' },
  { id: 'neutral', label: '中性' }
]

const SPECIES: { id: SpeciesKind; label: string }[] = [
  { id: 'wolf', label: '狼' },
  { id: 'fox', label: '狐' },
  { id: 'cat', label: '猫' },
  { id: 'dog', label: '狗' },
  { id: 'bear', label: '熊' },
  { id: 'rabbit', label: '兔' },
  { id: 'deer', label: '鹿' },
  { id: 'dragon', label: '龙' },
  { id: 'bird', label: '鸟' },
  { id: 'reptile', label: '爬行类' },
  { id: 'aquatic', label: '水生' },
  { id: 'insect', label: '昆虫' },
  { id: 'custom', label: '自定义' }
]

const BODY_TYPES: { id: BodyType; label: string }[] = [
  { id: 'humanoid', label: '人类直立' },
  { id: 'biped-anthro', label: '兽人直立' },
  { id: 'quadruped', label: '四足' },
  { id: 'bird', label: '鸟类' },
  { id: 'dragon', label: '龙形' },
  { id: 'custom', label: '自定义' }
]

const FUR_STYLES: { id: FurStyle; label: string }[] = [
  { id: 'none', label: '无' },
  { id: 'toon', label: 'Toon' },
  { id: 'anime', label: '动漫' },
  { id: 'stylized', label: '风格化' },
  { id: 'realistic', label: '写实' }
]

const TAILS: { id: TailMode; label: string }[] = [
  { id: 'none', label: '无尾' },
  { id: 'single', label: '单尾' },
  { id: 'multiple', label: '多尾' }
]

const FEATURES: { key: keyof AnatomyGraph; label: string }[] = [
  { key: 'ears', label: '耳' },
  { key: 'horns', label: '角' },
  { key: 'antlers', label: '鹿角' },
  { key: 'wings', label: '翼' },
  { key: 'snout', label: '口鼻' },
  { key: 'muzzle', label: '吻部' },
  { key: 'beak', label: '喙' },
  { key: 'paws', label: '爪掌' },
  { key: 'claws', label: '利爪' },
  { key: 'hooves', label: '蹄' },
  { key: 'fins', label: '鳍' },
  { key: 'tentacles', label: '触手' },
  { key: 'extraLimbs', label: '额外肢体' }
]

function isNonHumanType(t: CharacterType): boolean {
  return t !== 'human' && t !== 'anime-human'
}

export default function AIAssistantPanel(): JSX.Element {
  const spec = useProjectStore((s) => s.project.spec)
  const images = useProjectStore((s) => s.project.images)
  const updateSpec = useProjectStore((s) => s.updateSpec)

  const runGeneration = useGenerationStore((s) => s.runGeneration)
  const activeJobId = useGenerationStore((s) => s.activeJobId)
  const running = activeJobId !== null

  const backendOnline = useUIStore((s) => s.backendOnline)
  const providerId = useUIStore((s) => s.providerId)
  const setProviderId = useUIStore((s) => s.setProviderId)
  const selectedReferenceIds = useUIStore((s) => s.selectedReferenceIds)
  const toggleReference = useUIStore((s) => s.toggleReference)
  const checkBackend = useUIStore((s) => s.checkBackend)

  const [error, setError] = useState<string | null>(null)
  const [editInput, setEditInput] = useState('')
  const [editResult, setEditResult] = useState<string | null>(null)

  const selectedProvider = useMemo(() => providers.find((p) => p.id === providerId) ?? providers[0], [providerId])
  const selectedRefs = images.filter((i) => selectedReferenceIds.includes(i.id))
  const showCreature = isNonHumanType(spec.characterType)
  const rigProfile = useMemo(() => {
    const byType: Record<BodyType, (typeof RIG_PROFILES)[number]['id']> = {
      humanoid: 'humanoid',
      'biped-anthro': 'anthropomorphic',
      quadruped: 'quadruped',
      bird: 'bird',
      dragon: 'dragon',
      custom: 'custom'
    }
    return getRigProfile(byType[spec.bodyType] ?? 'humanoid')
  }, [spec.bodyType])

  useEffect(() => {
    void checkBackend()
  }, [providerId, checkBackend])

  const setCharacterType = (t: CharacterType): void => {
    const patch: Partial<typeof spec> = { characterType: t }
    if (t === 'anthro') {
      patch.bodyType = 'biped-anthro'
      patch.anatomy = { ...spec.anatomy, snout: true, ears: true, tail: 'single' }
    } else if (t === 'animal') {
      patch.bodyType = 'quadruped'
      patch.anatomy = { ...spec.anatomy, snout: true, ears: true, tail: 'single', paws: true }
    } else if (t === 'fantasy-creature') {
      patch.bodyType = 'dragon'
      patch.anatomy = { ...spec.anatomy, horns: true, tail: 'single', wings: true }
    } else {
      patch.bodyType = 'humanoid'
    }
    updateSpec(patch)
  }

  const setAnatomy = (key: keyof AnatomyGraph, value: boolean | TailMode): void => {
    updateSpec({ anatomy: { ...spec.anatomy, [key]: value } })
  }

  const setSpecies = (kind: SpeciesKind): void => {
    updateSpec({
      species: {
        ...spec.species,
        primary: kind,
        confidence: kind === 'custom' ? null : 0.9
      }
    })
  }

  const setFurStyle = (style: FurStyle): void => {
    updateSpec({ fur: { ...spec.fur, enabled: style !== 'none', style } })
  }

  const handleGenerate = async (): Promise<void> => {
    setError(null)
    if (selectedProvider.requiresBackend && !backendOnline) {
      setError('后端离线。请运行 `npm run backend` 启动，或切换为 Mock 提供方。')
      return
    }
    if (selectedRefs.length === 0) {
      setError('未选择参考图，将使用空白参考进行生成。')
    }
    try {
      await runGeneration(spec, selectedRefs, selectedProvider.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const handleInterpretEdit = async (): Promise<void> => {
    const input = editInput.trim()
    if (!input) return
    const interpreter = editInterpreters[0]
    const result = await interpreter.interpret(input, spec)
    setEditResult(`${result.message}\n${JSON.stringify(result.command, null, 2)}`)
  }

  return (
    <aside className="panel panel--right">
      <div className="panel__header">
        <span className="panel__title">
          <span className="panel__dot" />
          AI 助手
        </span>
      </div>

      <div className="panel__body">
        <div className="spec-field">
          <label>角色名称</label>
          <input value={spec.name} onChange={(e) => updateSpec({ name: e.target.value })} />
        </div>

        <div className="spec-field">
          <label>角色类型</label>
          <div className="chip-row">
            {CHARACTER_TYPES.map((t) => (
              <button
                key={t.id}
                className={`chip${spec.characterType === t.id ? ' chip--active' : ''}`}
                onClick={() => setCharacterType(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {showCreature && (
          <>
            <div className="spec-field">
              <label>物种</label>
              <div className="chip-row">
                {SPECIES.map((s) => (
                  <button
                    key={s.id}
                    className={`chip${spec.species.primary === s.id ? ' chip--active' : ''}`}
                    onClick={() => setSpecies(s.id)}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              {spec.species.primary === 'custom' && (
                <input
                  style={{ marginTop: 6 }}
                  placeholder="输入自定义物种（如：狐狸龙混合兽人）"
                  value={spec.species.label ?? ''}
                  onChange={(e) => updateSpec({ species: { ...spec.species, label: e.target.value } })}
                />
              )}
            </div>

            <div className="spec-field">
              <label>体型（骨骼模板）</label>
              <div className="chip-row">
                {BODY_TYPES.map((b) => (
                  <button
                    key={b.id}
                    className={`chip${spec.bodyType === b.id ? ' chip--active' : ''}`}
                    onClick={() => updateSpec({ bodyType: b.id })}
                  >
                    {b.label}
                  </button>
                ))}
              </div>
              <div className="provider-row" style={{ marginTop: 8 }}>
                当前模板：{rigProfile.label}（{rigProfile.bones.length} 根骨骼）
              </div>
            </div>

            <div className="spec-field">
              <label>毛发</label>
              <div className="chip-row">
                {FUR_STYLES.map((f) => (
                  <button
                    key={f.id}
                    className={`chip${spec.fur.enabled === (f.id !== 'none') && spec.fur.style === f.id ? ' chip--active' : ''}`}
                    onClick={() => setFurStyle(f.id)}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="spec-field">
              <label>尾巴</label>
              <div className="chip-row">
                {TAILS.map((t) => (
                  <button
                    key={t.id}
                    className={`chip${spec.anatomy.tail === t.id ? ' chip--active' : ''}`}
                    onClick={() => setAnatomy('tail', t.id)}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="spec-field">
              <label>特征部件</label>
              <div className="chip-row">
                {FEATURES.map((f) => (
                  <button
                    key={f.key}
                    className={`chip${spec.anatomy[f.key] === true ? ' chip--active' : ''}`}
                    onClick={() => setAnatomy(f.key, !spec.anatomy[f.key])}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        <div className="spec-field">
          <label>风格</label>
          <div className="chip-row">
            {STYLES.map((s) => (
              <button
                key={s.id}
                className={`chip${spec.style === s.id ? ' chip--active' : ''}`}
                onClick={() => updateSpec({ style: s.id })}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <div className="spec-field">
          <label>性别</label>
          <div className="chip-row">
            {GENDERS.map((g) => (
              <button
                key={g.id}
                className={`chip${spec.gender === g.id ? ' chip--active' : ''}`}
                onClick={() => updateSpec({ gender: g.id })}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>

        <div className="spec-field">
          <label>
            身高 — <span style={{ color: 'var(--accent)' }}>{spec.heightCm} cm</span>
          </label>
          <input
            type="range"
            min={100}
            max={220}
            step={1}
            value={spec.heightCm}
            onChange={(e) => updateSpec({ heightCm: Number(e.target.value) })}
          />
        </div>

        <div className="spec-field">
          <label>描述</label>
          <textarea
            placeholder="可用自然语言描述角色，如：这是一只半写实的狐狸龙混合兽人，有两条蓬松尾巴和一对短角。"
            value={spec.description}
            onChange={(e) => updateSpec({ description: e.target.value })}
          />
        </div>

        <div className="spec-field">
          <label>参考图（已选 {selectedReferenceIds.length} 张）</label>
          {images.length === 0 ? (
            <div className="empty-hint">请先在素材库导入参考图。</div>
          ) : (
            <div className="ref-grid">
              {images.map((img) => (
                <div
                  key={img.id}
                  className={`ref-thumb${selectedReferenceIds.includes(img.id) ? ' ref-thumb--selected' : ''}`}
                  onClick={() => toggleReference(img.id)}
                >
                  <img src={img.dataUrl} alt={img.name} />
                </div>
              ))}
            </div>
          )}
        </div>

        <VisionAnalysisPanel />

        <div className="spec-field">
          <label>自然语言编辑（Mock）</label>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              placeholder="例如：把尾巴变得更蓬松"
              value={editInput}
              onChange={(e) => setEditInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleInterpretEdit()
              }}
            />
            <button className="btn" onClick={() => void handleInterpretEdit()}>
              解析
            </button>
          </div>
          {editResult && (
            <pre
              style={{
                marginTop: 8,
                fontSize: 11,
                color: 'var(--text-dim)',
                whiteSpace: 'pre-wrap',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: 8,
                lineHeight: 1.5
              }}
            >
              {editResult}
            </pre>
          )}
        </div>

        <div className="spec-field">
          <label>生成提供方</label>
          <div className="chip-row">
            {providers.map((p) => (
              <button
                key={p.id}
                className={`chip${providerId === p.id ? ' chip--active' : ''}`}
                title={p.description}
                onClick={() => setProviderId(p.id)}
              >
                {p.name}
              </button>
            ))}
          </div>
          <div className="provider-row" style={{ marginTop: 8 }}>
            {selectedProvider.requiresBackend ? (
              <>
                <span className={`provider-dot ${backendOnline ? 'provider-dot--ok' : 'provider-dot--off'}`} />
                {backendOnline ? '后端已连接' : '后端离线'}
              </>
            ) : (
              <>
                <span className="provider-dot provider-dot--ok" />
                本地运行 · 无需 AI API
              </>
            )}
          </div>
        </div>

        {error && (
          <div style={{ color: 'var(--danger)', fontSize: 12, marginTop: 4 }}>{error}</div>
        )}
      </div>

      <div className="panel__footer">
        <button
          className="btn btn--primary btn--block"
          disabled={running}
          onClick={() => void handleGenerate()}
        >
          {running ? '生成中…' : '生成角色'}
        </button>
        <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 8, lineHeight: 1.5 }}>
          {selectedProvider.description}
        </div>
      </div>
    </aside>
  )
}
