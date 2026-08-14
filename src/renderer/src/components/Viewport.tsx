import { useEffect, useRef, useState } from 'react'
import { ViewportManager } from '../three/ViewportManager'
import type { CameraPreset } from '../three/ViewportManager'
import { setViewportManager } from '../three/controller'
import { demoUrlForId, loadDemoCharacterBytes } from '../core/demo/demoCharacter'
import { formatDimensions } from '../core/spec/modelInfoLogic'
import { useProjectStore } from '../store/projectStore'
import { useUIStore } from '../store/uiStore'

const PRESETS: { id: CameraPreset; label: string }[] = [
  { id: 'front', label: '前' },
  { id: 'back', label: '后' },
  { id: 'left', label: '左' },
  { id: 'right', label: '右' },
  { id: 'top', label: '顶' },
  { id: 'iso', label: '透视' }
]

interface Hud {
  dimensions: string | null
  meshCount: number | null
}

export default function Viewport(): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const managerRef = useRef<ViewportManager | null>(null)

  const selectedModelId = useProjectStore((s) => s.selectedModelId)
  const modelBuffers = useProjectStore((s) => s.modelBuffers)
  const models = useProjectStore((s) => s.project.models)
  const cameraPreset = useUIStore((s) => s.cameraPreset)
  const setCameraPreset = useUIStore((s) => s.setCameraPreset)

  const [hud, setHud] = useState<Hud | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const manager = new ViewportManager(containerRef.current)
    managerRef.current = manager
    setViewportManager(manager)
    return () => {
      setViewportManager(null)
      managerRef.current = null
      setHud(null)
      manager.dispose()
    }
  }, [])

  useEffect(() => {
    void (async () => {
      const vp = managerRef.current
      if (!vp) return
      // Clear any previous model info immediately so switching/failure never
      // leaves stale dimensions behind.
      setHud(null)
      try {
        if (selectedModelId && demoUrlForId(selectedModelId)) {
          const bytes = await loadDemoCharacterBytes(selectedModelId)
          await vp.loadGLB(bytes)
        } else if (selectedModelId && modelBuffers[selectedModelId]) {
          await vp.loadGLB(modelBuffers[selectedModelId])
        } else {
          return
        }
        const info = vp.getModelInfo()
        const model = models.find((m) => m.id === selectedModelId)
        setHud({
          // World-space Box3 from the live viewport (after load).
          dimensions: info?.dimensions ? formatDimensions(info.dimensions) : null,
          // mesh count only comes from backend analyzer stats - never guessed.
          meshCount: model?.glbStats?.meshCount ?? null
        })
      } catch (err) {
        console.error('Failed to load model into viewport:', err)
        setHud(null)
      }
    })()
  }, [selectedModelId, modelBuffers, models])

  useEffect(() => {
    managerRef.current?.setCameraPreset(cameraPreset)
  }, [cameraPreset])

  return (
    <div className="viewport" ref={containerRef}>
      <div className="viewport__overlay">
        <div className="camera-preset">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              className={cameraPreset === p.id ? 'active' : ''}
              onClick={() => setCameraPreset(p.id)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <div className="viewport__hint">左键拖拽旋转 · 滚轮缩放 · 右键拖拽平移</div>
      {hud?.dimensions && (
        <div
          style={{
            position: 'absolute',
            left: 10,
            bottom: 10,
            zIndex: 5,
            fontSize: 11.5,
            color: 'var(--text-dim)',
            background: 'rgba(11,14,20,0.7)',
            border: '1px solid var(--border)',
            padding: '4px 10px',
            borderRadius: 6
          }}
        >
          视口尺寸：{hud.dimensions}
          {hud.meshCount != null && ` · ${hud.meshCount} 网格`}
        </div>
      )}
    </div>
  )
}
