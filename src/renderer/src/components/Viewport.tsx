import { useEffect, useRef } from 'react'
import { ViewportManager } from '../three/ViewportManager'
import type { CameraPreset } from '../three/ViewportManager'
import { setViewportManager } from '../three/controller'
import { demoUrlForId, loadDemoCharacterBytes } from '../core/demo/demoCharacter'
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

export default function Viewport(): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const managerRef = useRef<ViewportManager | null>(null)

  const selectedModelId = useProjectStore((s) => s.selectedModelId)
  const modelBuffers = useProjectStore((s) => s.modelBuffers)
  const cameraPreset = useUIStore((s) => s.cameraPreset)
  const setCameraPreset = useUIStore((s) => s.setCameraPreset)

  useEffect(() => {
    if (!containerRef.current) return
    const manager = new ViewportManager(containerRef.current)
    managerRef.current = manager
    setViewportManager(manager)
    return () => {
      setViewportManager(null)
      managerRef.current = null
      manager.dispose()
    }
  }, [])

  useEffect(() => {
    void (async () => {
      const vp = managerRef.current
      if (!vp) return
      try {
        if (selectedModelId && demoUrlForId(selectedModelId)) {
          const bytes = await loadDemoCharacterBytes(selectedModelId)
          await vp.loadGLB(bytes)
        } else if (selectedModelId && modelBuffers[selectedModelId]) {
          await vp.loadGLB(modelBuffers[selectedModelId])
        }
      } catch (err) {
        console.error('Failed to load model into viewport:', err)
      }
    })()
  }, [selectedModelId, modelBuffers])

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
    </div>
  )
}
