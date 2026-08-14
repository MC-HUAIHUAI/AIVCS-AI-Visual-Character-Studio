import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

export type CameraPreset = 'front' | 'back' | 'left' | 'right' | 'top' | 'iso'

export interface ModelInfo {
  dimensions: { x: number; y: number; z: number }
  center: { x: number; y: number; z: number }
  bounds: { min: [number, number, number]; max: [number, number, number] }
}

interface TweenTarget {
  pos: THREE.Vector3
  target: THREE.Vector3
  t: number
}

const PRESETS: Record<CameraPreset, { pos: [number, number, number]; target: [number, number, number] }> = {
  iso: { pos: [3.1, 2.4, 3.6], target: [0, 0.8, 0] },
  front: { pos: [0, 1.15, 4.4], target: [0, 0.8, 0] },
  back: { pos: [0, 1.15, -4.4], target: [0, 0.8, 0] },
  left: { pos: [-4.4, 1.15, 0], target: [0, 0.8, 0] },
  right: { pos: [4.4, 1.15, 0], target: [0, 0.8, 0] },
  top: { pos: [0, 4.6, 0.01], target: [0, 0, 0] }
}

/**
 * Owns the WebGL scene, camera and controls for the central viewport.
 * The React layer only talks to this class through imperative methods.
 */
export class ViewportManager {
  private renderer: THREE.WebGLRenderer
  private scene: THREE.Scene
  private camera: THREE.PerspectiveCamera
  private controls: OrbitControls
  private container: HTMLElement
  private resizeObserver: ResizeObserver
  private raf = 0
  private clock = new THREE.Clock()
  private modelRoot: THREE.Group | null = null
  private tween: TweenTarget | null = null

  constructor(container: HTMLElement) {
    this.container = container

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.setSize(container.clientWidth, container.clientHeight)
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.1
    container.appendChild(this.renderer.domElement)

    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0x0b0e14)

    this.camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100)
    this.camera.position.set(3.1, 2.4, 3.6)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.target.set(0, 0.8, 0)
    this.controls.minDistance = 0.5
    this.controls.maxDistance = 20
    this.controls.maxPolarAngle = Math.PI * 0.92

    this.buildEnvironment()

    this.resizeObserver = new ResizeObserver(() => this.onResize())
    this.resizeObserver.observe(container)

    this.animate()
  }

  private buildEnvironment(): void {
    const hemi = new THREE.HemisphereLight(0xbfd4ff, 0x14181f, 1.0)
    this.scene.add(hemi)

    const key = new THREE.DirectionalLight(0xffffff, 2.2)
    key.position.set(3.5, 5.5, 3)
    key.castShadow = true
    key.shadow.mapSize.set(1024, 1024)
    key.shadow.camera.near = 0.5
    key.shadow.camera.far = 16
    key.shadow.camera.left = -3
    key.shadow.camera.right = 3
    key.shadow.camera.top = 4
    key.shadow.camera.bottom = -2
    key.shadow.bias = -0.0004
    this.scene.add(key)

    const fill = new THREE.DirectionalLight(0x9fb4ff, 0.55)
    fill.position.set(-3, 2, -2)
    this.scene.add(fill)

    const grid = new THREE.GridHelper(12, 24, 0x232c3d, 0x171d29)
    grid.position.y = -0.001
    this.scene.add(grid)

    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(6, 48),
      new THREE.MeshStandardMaterial({ color: 0x0f141d, roughness: 1 })
    )
    ground.rotation.x = -Math.PI / 2
    ground.position.y = 0
    ground.receiveShadow = true
    this.scene.add(ground)
  }

  /**
   * Loads a GLB/glTF from raw bytes and replaces the current character.
   */
  async loadGLB(bytes: ArrayBuffer): Promise<void> {
    const loader = new GLTFLoader()
    const gltf = await loader.parseAsync(bytes, '')
    this.setModel(gltf.scene)
  }

  private setModel(root: THREE.Object3D): void {
    this.clearModel()
    const group = new THREE.Group()
    group.add(root)
    group.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.castShadow = true
        obj.receiveShadow = true
      }
    })
    this.modelRoot = group
    this.scene.add(group)
    this.fitToModel()
  }

  clearModel(): void {
    if (this.modelRoot) {
      this.scene.remove(this.modelRoot)
      this.modelRoot.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry.dispose()
          const mat = obj.material as THREE.Material | THREE.Material[]
          if (Array.isArray(mat)) mat.forEach((m) => m.dispose())
          else mat.dispose()
        }
      })
      this.modelRoot = null
    }
  }

  /** The currently displayed model root, or null when the scene is empty. */
  getModelRoot(): THREE.Group | null {
    return this.modelRoot
  }

  /**
   * Pure read of the loaded model's WORLD-space Box3 (after load). Does not
   * modify geometry and never affects fitToModel behavior. Returns null when
   * no model is loaded or the bounds are empty.
   */
  getModelInfo(): ModelInfo | null {
    if (!this.modelRoot) return null
    const box = new THREE.Box3().setFromObject(this.modelRoot)
    if (box.isEmpty()) return null
    const size = box.getSize(new THREE.Vector3())
    const center = box.getCenter(new THREE.Vector3())
    const min = box.min
    const max = box.max
    const r = (v: number): number => Math.round(v * 10000) / 10000
    return {
      dimensions: { x: r(size.x), y: r(size.y), z: r(size.z) },
      center: { x: r(center.x), y: r(center.y), z: r(center.z) },
      bounds: {
        min: [r(min.x), r(min.y), r(min.z)],
        max: [r(max.x), r(max.y), r(max.z)]
      }
    }
  }

  private fitToModel(): void {
    if (!this.modelRoot) return
    const box = new THREE.Box3().setFromObject(this.modelRoot)
    const size = box.getSize(new THREE.Vector3())
    const center = box.getCenter(new THREE.Vector3())
    const dist = Math.max(size.length(), 1) * 2.2
    const dir = new THREE.Vector3(1, 0.55, 1).normalize()
    this.controls.target.copy(center)
    this.camera.position.copy(center).addScaledVector(dir, dist)
  }

  setCameraPreset(preset: CameraPreset): void {
    const p = PRESETS[preset]
    this.tween = {
      pos: new THREE.Vector3(...p.pos),
      target: new THREE.Vector3(...p.target),
      t: 0
    }
  }

  private onResize(): void {
    const w = this.container.clientWidth || 1
    const h = this.container.clientHeight || 1
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(w, h)
  }

  private animate = (): void => {
    this.raf = requestAnimationFrame(this.animate)
    const dt = Math.min(this.clock.getDelta(), 0.05)

    if (this.tween) {
      this.tween.t = Math.min(this.tween.t + dt * 2.2, 1)
      const e = 1 - Math.pow(1 - this.tween.t, 3)
      this.camera.position.lerp(this.tween.pos, e)
      this.controls.target.lerp(this.tween.target, e)
      if (this.tween.t >= 1) this.tween = null
    }

    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }

  dispose(): void {
    cancelAnimationFrame(this.raf)
    this.resizeObserver.disconnect()
    this.clearModel()
    this.scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh) obj.geometry.dispose()
    })
    this.renderer.dispose()
    this.renderer.domElement.remove()
  }
}
