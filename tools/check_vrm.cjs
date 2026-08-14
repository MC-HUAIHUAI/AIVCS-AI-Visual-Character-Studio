#!/usr/bin/env node
/**
 * @pixiv/three-vrm loader hard gate (Phase 2.7-C).
 *
 * Loads a .vrm with GLTFLoader + VRMLoaderPlugin and asserts:
 *   - the VRM object was created (userData.vrm)
 *   - vrm.humanoid exists and all 15 REQUIRED human bones resolve to raw nodes
 *   - scene contains a SkinnedMesh with a non-empty skeleton
 *   - GLB bounds are non-empty
 *   - the same file loads a second time successfully
 * Prints `VRM_OK bones=<n> skinned=<m> sizeY=<y>` on success. Exits non-zero on
 * any failure.
 *
 * Usage: node tools/check_vrm.cjs <path-to.vrm>
 */

const THREE = require('three')
const { GLTFLoader } = require('three/examples/jsm/loaders/GLTFLoader.js')
const { VRMLoaderPlugin } = require('@pixiv/three-vrm')
const fs = require('fs')

const REQUIRED_HUMAN_BONES = [
  'hips', 'spine', 'head',
  'leftUpperLeg', 'leftLowerLeg', 'leftFoot',
  'rightUpperLeg', 'rightLowerLeg', 'rightFoot',
  'leftUpperArm', 'leftLowerArm', 'leftHand',
  'rightUpperArm', 'rightLowerArm', 'rightHand'
]

const file = process.argv[2]
if (!file) {
  console.error('VRM_FAIL: no file path')
  process.exit(1)
}

function load(data) {
  return new Promise((resolve, reject) => {
    const loader = new GLTFLoader()
    loader.register((parser) => new VRMLoaderPlugin(parser))
    loader.parse(data, '', (gltf) => resolve(gltf), (err) => reject(err))
  })
}

async function main() {
  const buf = fs.readFileSync(file)
  const data = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength)

  const gltf = await load(data)
  const problems = []

  const vrm = gltf.userData.vrm
  if (!vrm) {
    problems.push('no VRM in userData')
  } else if (!vrm.humanoid) {
    problems.push('no humanoid')
  } else {
    const missing = REQUIRED_HUMAN_BONES.filter((b) => !vrm.humanoid.getRawBoneNode(b))
    if (missing.length) problems.push('missing required bones: ' + missing.join(','))
  }

  let skinned = 0
  let bones = 0
  gltf.scene.traverse((o) => {
    if (o.isSkinnedMesh) {
      skinned += 1
      if (o.skeleton) bones = o.skeleton.bones.length
    }
  })
  if (skinned === 0) problems.push('no SkinnedMesh')
  if (bones === 0) problems.push('no skeleton bones')

  const box = new THREE.Box3().setFromObject(gltf.scene)
  const size = box.getSize(new THREE.Vector3())
  if (size.length() < 0.001) problems.push('empty bounds')

  try {
    await load(data)
  } catch (err) {
    problems.push('second load failed: ' + (err && err.message ? err.message : err))
  }

  if (problems.length) {
    console.error('VRM_FAIL: ' + problems.join(' | '))
    process.exit(1)
  }
  console.log('VRM_OK bones=' + bones + ' skinned=' + skinned + ' sizeY=' + size.y.toFixed(2))
  process.exit(0)
}

main().catch((err) => {
  console.error('VRM_FAIL: ' + (err && err.message ? err.message : err))
  process.exit(1)
})
