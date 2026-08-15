#!/usr/bin/env node
/**
 * Frontend model-info logic tests (Phase 2.5-C).
 *
 * Runs against tsc-compiled CommonJS output in .review-test/ (no framework).
 * Build first: npm run test:frontend
 */

import { strict as assert } from 'node:assert'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const logic = require('../.review-test/renderer/src/core/spec/modelInfoLogic.js')

const { formatBytes, formatDimensions, formatVec3, buildModelInfoRows } = logic

let passed = 0
function check(name, fn) {
  try {
    fn()
    passed += 1
    console.log(`  ok - ${name}`)
  } catch (err) {
    console.error(`  FAIL - ${name}\n    ${err.message}`)
    process.exitCode = 1
  }
}

console.log('Phase 2.5-C model info logic')

const stats = {
  format: 'glb',
  version: 2,
  sizeBytes: 111857,
  meshCount: 17,
  primitiveCount: 17,
  vertexCount: 2244,
  indexCount: 11484,
  triangleCount: 3828,
  materialCount: 9,
  textureCount: 0,
  hasNormals: true,
  hasUVs: false,
  bounds: { min: [-0.47, 0, -0.38], max: [0.47, 1.77, 0.39] },
  dimensions: { x: 0.94, y: 1.77, z: 0.77 },
  center: { x: 0, y: 0.885, z: 0.005 },
  meshStats: [],
  warnings: ['bounds 基于 accessor 局部坐标（未应用节点变换）']
}

check('formatBytes', () => {
  assert.equal(formatBytes(111857), '109.2 KB')
  assert.equal(formatBytes(512), '512 B')
  assert.equal(formatBytes(undefined), null)
})

check('formatDimensions', () => {
  assert.equal(formatDimensions({ x: 1.2, y: 1.83, z: 0.7 }), '1.20 × 1.83 × 0.70 m')
})

check('formatVec3', () => {
  assert.equal(formatVec3([-0.5, 0.25, 1]), '(-0.500, 0.250, 1.000)')
  assert.equal(formatVec3(undefined), null)
})

check('with stats -> rows populated', () => {
  const { rows, warnings, normalizations } = buildModelInfoRows(
    { glbStats: stats, sizeBytes: 111857, texture: { supported: true, kind: 'paint', maps: { baseColor: true, normal: true, metallicRoughness: false }, textureCount: 1, hasUVs: true } },
    { bodyType: 'humanoid' }
  )
  const map = Object.fromEntries(rows.filter((r) => r.value !== null).map((r) => [r.label, r.value]))
  assert.equal(map['文件大小'], '109.2 KB')
  assert.equal(map['GLB 版本'], 'glTF 2')
  assert.equal(map['网格数'], '17')
  assert.equal(map['顶点数'], '2244')
  assert.equal(map['三角形数'], '3828')
  assert.equal(map['材质数'], '9')
  assert.equal(map['纹理状态'], 'BaseColor + Normal')
  assert.equal(map['VRM 状态'], '未绑定（可转换为 VRM）')
  assert.equal(map['法线'], '有')
  assert.equal(map['UV'], '无')
  assert.equal(map['GLB 分析尺寸（局部坐标）'], '0.94 × 1.77 × 0.77 m')
  assert.equal(map['Bounds min'], '(-0.470, 0.000, -0.380)')
  assert.deepEqual(warnings, ['bounds 基于 accessor 局部坐标（未应用节点变换）'])
  assert.deepEqual(normalizations, [])
})

check('without stats -> stats rows null, texture/vrm defaults present', () => {
  const { rows, warnings, normalizations } = buildModelInfoRows({})
  const map = Object.fromEntries(rows.map((r) => [r.label, r.value]))
  assert.equal(map['文件大小'], null)
  assert.equal(map['顶点数'], null)
  assert.equal(map['纹理状态'], '无纹理（shape-only）')
  assert.equal(map['VRM 状态'], '未绑定')
  assert.deepEqual(warnings, [])
  assert.deepEqual(normalizations, [])
})

check('normalizations shown only when present', () => {
  const empty = buildModelInfoRows({})
  assert.deepEqual(empty.normalizations, [])
  const withNotes = buildModelInfoRows({ normalizations: ['Y-up 校验通过'] })
  assert.deepEqual(withNotes.normalizations, ['Y-up 校验通过'])
})

check('model switch does not cross-talk (pure function, no shared state)', () => {
  const a = buildModelInfoRows({ glbStats: stats })
  const b = buildModelInfoRows({})
  const aRows = a.rows.filter((r) => r.value !== null)
  assert.ok(aRows.length > 0)
  assert.equal(b.rows.find((r) => r.label === '顶点数').value, null)
  // calling A again still yields the same data
  const a2 = buildModelInfoRows({ glbStats: stats })
  assert.deepEqual(a2.rows, a.rows)
})

check('empty model state', () => {
  const out = buildModelInfoRows({})
  assert.equal(out.rows.length > 0, true)
  assert.equal(out.rows.find((r) => r.label === '顶点数').value, null)
  assert.deepEqual(out.warnings, [])
})

// ---- Phase 3-J: texture / skeleton / VRM status ----

check('textureStatusLabel', () => {
  assert.equal(logic.textureStatusLabel({}), '无纹理（shape-only）')
  assert.equal(
    logic.textureStatusLabel({ texture: { supported: true, kind: 'paint', maps: { baseColor: true, normal: true, metallicRoughness: true } } }),
    'BaseColor + Normal + MetallicRoughness'
  )
  assert.equal(
    logic.textureStatusLabel({ texture: { supported: true, kind: 'paint', maps: { baseColor: false, normal: false, metallicRoughness: false } } }),
    '有纹理'
  )
})

check('canConvertToVrm', () => {
  assert.equal(logic.canConvertToVrm('humanoid'), true)
  assert.equal(logic.canConvertToVrm('biped-anthro'), true)
  assert.equal(logic.canConvertToVrm('custom'), true)
  assert.equal(logic.canConvertToVrm('quadruped'), false)
  assert.equal(logic.canConvertToVrm('bird'), false)
  assert.equal(logic.canConvertToVrm('dragon'), false)
  assert.equal(logic.canConvertToVrm(null), false)
  assert.equal(logic.canConvertToVrm(undefined), false)
})

check('vrmStatusForModel states', () => {
  const bt = (bodyType) => ({ hasDerivedVrm: false, bodyType })
  // VRM model -> bound
  assert.equal(logic.vrmStatusForModel({ format: 'vrm' }, bt('humanoid')).state, 'bound')
  // derived VRM exists -> bound
  assert.equal(logic.vrmStatusForModel({ format: 'glb' }, { hasDerivedVrm: true, bodyType: 'humanoid' }).state, 'bound')
  // humanoid -> bindable
  assert.equal(logic.vrmStatusForModel({ format: 'glb' }, bt('humanoid')).state, 'bindable')
  // non-human -> unsupported (never attempted)
  assert.equal(logic.vrmStatusForModel({ format: 'glb' }, bt('quadruped')).state, 'unsupported')
  // unknown body type -> neutral unbound
  assert.equal(logic.vrmStatusForModel({ format: 'glb' }, bt(null)).state, 'unbound')
})

check('skinned skeleton row', () => {
  const map = (s) => Object.fromEntries(buildModelInfoRows({ glbStats: s }).rows.map((r) => [r.label, r.value]))
  assert.equal(map({ ...stats, skinned: true })['骨骼状态'], '有骨骼（skinned）')
  assert.equal(map({ ...stats, skinned: false })['骨骼状态'], '无骨骼（静态网格）')
  assert.equal(map(stats)['骨骼状态'], null) // skinned unknown -> no guess
})

console.log(`\n${passed} checks passed`)
