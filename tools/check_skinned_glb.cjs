#!/usr/bin/env node
/**
 * Three.js SkinnedMesh hard gate (Phase 2.6-B).
 *
 * Loads a GLB and asserts:
 *   - at least one SkinnedMesh exists
 *   - mesh.skeleton exists and bones.length > 0
 *   - JOINTS_0 / WEIGHTS_0 exist (three exposes them as skinIndex / skinWeight)
 *   - model bounds are sane (non-empty)
 * Prints `SKINNED_OK bones=<n>` on success so the caller can cross-check the
 * bone count against skins[0].joints.length. Exits non-zero on any failure.
 *
 * Usage: node tools/check_skinned_glb.cjs <path-to.glb>
 */

const THREE = require('three')
const { GLTFLoader } = require('three/examples/jsm/loaders/GLTFLoader.js')
const fs = require('fs')

const file = process.argv[2]
if (!file) {
  console.error('FAIL no file path')
  process.exit(1)
}

const buf = fs.readFileSync(file)
const data = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength)

new GLTFLoader()
  .parseAsync(data, '')
  .then((gltf) => {
    let skinned = 0
    let bones = 0
    const problems = []
    gltf.scene.traverse((o) => {
      if (o.isSkinnedMesh) {
        skinned += 1
        if (!o.skeleton) problems.push('no skeleton')
        else bones = o.skeleton.bones.length
        const geo = o.geometry
        if (!geo.getAttribute('skinIndex')) problems.push('missing JOINTS_0/skinIndex')
        if (!geo.getAttribute('skinWeight')) problems.push('missing WEIGHTS_0/skinWeight')
        if (o.skeleton && o.skeleton.bones.length === 0) problems.push('zero bones')
      }
    })
    if (skinned === 0) problems.push('no SkinnedMesh')
    if (bones === 0) problems.push('zero bones in skeleton')

    const box = new THREE.Box3().setFromObject(gltf.scene)
    const size = box.getSize(new THREE.Vector3())
    if (size.length() < 0.001) problems.push('empty bounds')

    if (problems.length > 0) {
      console.error('FAIL: ' + problems.join(', '))
      process.exit(1)
    }
    console.log('SKINNED_OK bones=' + bones + ' meshes=' + skinned + ' sizeY=' + size.y.toFixed(2))
    process.exit(0)
  })
  .catch((err) => {
    console.error('FAIL: ' + (err && err.message ? err.message : String(err)))
    process.exit(1)
  })
