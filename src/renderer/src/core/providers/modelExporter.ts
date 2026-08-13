import { GLTFExporter } from 'three/examples/jsm/exporters/GLTFExporter.js'
import type * as THREE from 'three'
import type { ModelFormat } from '@shared/types'

export interface ExportModelOptions {
  binary: boolean
  name: string
}

export interface ExportModelOutput {
  /** base64 data URL ready to be persisted via the main process. */
  dataUrl: string
  /** e.g. "character.glb" */
  fileName: string
  format: ModelFormat
  byteLength: number
}

/**
 * Model exporter contract. Implementations know how to serialize a Three.js
 * scene graph into a portable 3D asset format.
 *
 * GLB/GLTF are supported now; VRM and Live2D will be added behind this same
 * interface later.
 */
export interface IModelExporter {
  readonly format: ModelFormat
  exportModel(root: THREE.Object3D, options: ExportModelOptions): Promise<ExportModelOutput>
}

function toDataUrl(buffer: ArrayBuffer, mime: string): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + chunk)))
  }
  return `data:${mime};base64,${btoa(binary)}`
}

/**
 * Serializes the scene to glTF. Uses three's GLTFExporter under the hood.
 * Note: a placeholder EmptyNode is used to keep this import decoupled from the
 * viewport's scene graph.
 */
export class GLBExporter implements IModelExporter {
  readonly format: ModelFormat = 'glb'

  async exportModel(root: THREE.Object3D, options: ExportModelOptions): Promise<ExportModelOutput> {
    const exporter = new GLTFExporter()
    const binary = await exporter.parseAsync(root, {
      binary: options.binary,
      embedImages: true
    })

    const bytes = binary as ArrayBuffer
    const dataUrl = toDataUrl(bytes, 'model/gltf-binary')
    const ext = options.binary ? 'glb' : 'gltf'
    return {
      dataUrl,
      fileName: `${options.name}.${ext}`,
      format: options.binary ? 'glb' : 'gltf',
      byteLength: bytes.byteLength
    }
  }
}

/** Future Live2D export will be implemented against this same interface. */
export class Live2DExporter implements IModelExporter {
  readonly format: ModelFormat = 'l2d'

  async exportModel(_root: THREE.Object3D, _options: ExportModelOptions): Promise<ExportModelOutput> {
    throw new Error('Live2D export is not implemented yet')
  }
}

/** Future VRM export will be implemented against this same interface. */
export class VRMExporter implements IModelExporter {
  readonly format: ModelFormat = 'vrm'

  async exportModel(_root: THREE.Object3D, _options: ExportModelOptions): Promise<ExportModelOutput> {
    throw new Error('VRM export is not implemented yet')
  }
}

export const modelExporters: Record<string, IModelExporter> = {
  glb: new GLBExporter(),
  gltf: new GLBExporter(),
  l2d: new Live2DExporter(),
  vrm: new VRMExporter()
}
