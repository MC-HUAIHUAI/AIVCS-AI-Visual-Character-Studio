#!/usr/bin/env node
/**
 * Frontend image-to-3d generation logic tests (Phase 2.3-C).
 *
 * Runs against tsc-compiled CommonJS output in .review-test/ (no framework).
 * Build first: npm run test:frontend
 */

import { strict as assert } from 'node:assert'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const logic = require('../.review-test/renderer/src/core/spec/generationLogic.js')

const {
  isTerminal,
  shouldPoll,
  canRetry,
  canCancel,
  referencesWithinLimit,
  buildGenerationRequest,
  createQueuedJob,
  retryJobFrom,
  applyDtoToJob,
  modelAssetFromResult,
  statusText
} = logic

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

const spec = { id: 's', name: 't', characterType: 'human' }
const refs = [{ id: 'a', dataUrl: 'data:image/png;base64,AA', view: 'front' }]

console.log('Phase 2.3-C frontend generation logic')

// 1-6 polling / terminal
check('1. queued -> polling', () => assert.ok(shouldPoll('queued')))
check('2. running -> polling', () => assert.ok(shouldPoll('running')))
check('3. done -> stop polling', () => {
  assert.ok(!shouldPoll('done'))
  assert.ok(isTerminal('done'))
})
check('4. failed -> stop polling', () => {
  assert.ok(!shouldPoll('failed'))
  assert.ok(isTerminal('failed'))
})
check('5. timed_out -> stop polling', () => {
  assert.ok(!shouldPoll('timed_out'))
  assert.ok(isTerminal('timed_out'))
})
check('6. cancelled -> stop polling', () => {
  assert.ok(!shouldPoll('cancelled'))
  assert.ok(isTerminal('cancelled'))
})

// 7-8 cancel once, no double send
check('7. cancel allowed while running', () => {
  assert.ok(canCancel('running'))
  assert.ok(canCancel('queued'))
})
check('7b. cancel guard sends once and blocks repeats', () => {
  const signal = { aborted: false }
  const guard = (status) => {
    if (isTerminal(status) || signal.aborted) return false
    signal.aborted = true
    return true
  }
  assert.equal(guard('running'), true) // first send
  assert.equal(guard('running'), false) // no double send
  assert.ok(signal.aborted)
})
check('8. done cannot be cancelled', () => assert.ok(!canCancel('done')))

// 9-12 retry rules
check('9. failed retry -> brand new job', () => {
  const prev = createQueuedJob('old', 'mock', 1)
  const next = retryJobFrom(prev, 'new-job-id')
  assert.notEqual(next.id, prev.id)
  assert.equal(next.id, 'new-job-id')
  assert.equal(next.attempt, 2)
  assert.equal(next.status, 'queued')
  assert.ok(canRetry('failed'))
})
check('10. timed_out retry -> brand new job', () => {
  assert.ok(canRetry('timed_out'))
  const prev = createQueuedJob('old2', 'mock', 2)
  const next = retryJobFrom(prev, 'new2')
  assert.equal(next.attempt, 3)
  assert.equal(next.resultModelId, null)
})
check('11. cancelled not auto-retryable', () => assert.ok(!canRetry('cancelled')))
check('12. done not retryable', () => assert.ok(!canRetry('done')))

// 13 ModelAsset metadata mapping
check('13. ModelAsset metadata mapped from job result', () => {
  const asset = modelAssetFromResult('m1', 'generated_character', {
    format: 'glb',
    mime: 'model/gltf-binary',
    sizeBytes: 111857,
    providerId: 'Mock',
    sourceJobId: 'job42'
  })
  assert.equal(asset.id, 'm1')
  assert.equal(asset.format, 'glb')
  assert.equal(asset.mime, 'model/gltf-binary')
  assert.equal(asset.sizeBytes, 111857)
  assert.equal(asset.providerId, 'Mock')
  assert.equal(asset.sourceJobId, 'job42')
  assert.equal(asset.source, 'generated')
  assert.equal(asset.glbStats, undefined) // absent stats -> undefined (backward compatible)
})

// 13b glbStats pass-through
check('13b. glbStats passed through from job result (no guessing)', () => {
  const stats = {
    format: 'glb',
    version: 2,
    sizeBytes: 111857,
    meshCount: 17,
    primitiveCount: 17,
    vertexCount: 100,
    indexCount: 150,
    triangleCount: 50,
    materialCount: 9,
    textureCount: 0,
    hasNormals: true,
    hasUVs: false,
    bounds: { min: [0, 0, 0], max: [1, 1, 1] },
    dimensions: { x: 1, y: 1, z: 1 },
    center: { x: 0.5, y: 0.5, z: 0.5 },
    meshStats: [],
    warnings: []
  }
  const asset = modelAssetFromResult('m2', 'generated_character', { glbStats: stats })
  assert.deepEqual(asset.glbStats, stats)
})

// 14 references limit
check('14. references at most 4', () => {
  const five = Array.from({ length: 5 }, (_, i) => ({ id: `i${i}` }))
  const four = Array.from({ length: 4 }, (_, i) => ({ id: `i${i}` }))
  assert.ok(!referencesWithinLimit(five))
  assert.ok(referencesWithinLimit(four))
  assert.ok(referencesWithinLimit([]))
})

// 15 old request without references stays compatible
check('15. old request (no references) compatible', () => {
  const req = buildGenerationRequest(spec, [])
  assert.deepEqual(req.references, [])
  assert.equal(req.timeoutSeconds, undefined)
  const withRefs = buildGenerationRequest(spec, refs, 60)
  assert.equal(withRefs.references.length, 1)
  assert.equal(withRefs.references[0].imageId, 'a')
  assert.equal(withRefs.timeoutSeconds, 60)
})

// extra: DTO mapping
check('extra. applyDtoToJob maps terminal states and metadata', () => {
  const base = createQueuedJob('j', 'mock', 1)
  const dto = {
    job_id: 'bj',
    status: 'timed_out',
    progress: 0.5,
    message: '生成超时',
    steps: [{ index: 0, label: '拓扑', status: 'running' }],
    error: '生成超时',
    result: null,
    retryable: true,
    timed_out: true,
    attempt: 2
  }
  const updated = applyDtoToJob(base, dto)
  assert.equal(updated.status, 'timed_out')
  assert.equal(updated.progress, 50)
  assert.equal(updated.steps[0].label, '拓扑')
  assert.equal(updated.retryable, true)
  assert.equal(updated.timedOut, true)
  assert.equal(updated.attempt, 2)
  assert.equal(statusText('cancelled'), '已取消')
})

// Phase 3-J: model asset carries texture metadata + VRM source linkage
check('modelAssetFromResult carries texture + sourceModelId', () => {
  const texture = { supported: true, kind: 'paint', maps: { baseColor: true, normal: false, metallicRoughness: false }, textureCount: 1, hasUVs: true }
  const asset = logic.modelAssetFromResult('m9', 'painted', {
    format: 'glb',
    providerId: 'hunyuan3d-2mini-paint',
    sourceJobId: 'job9',
    texture,
    sourceModelId: 'src-1'
  })
  assert.deepEqual(asset.texture, texture)
  assert.equal(asset.sourceModelId, 'src-1')
  assert.equal(asset.providerId, 'hunyuan3d-2mini-paint')
  // absent texture stays undefined (shape-only default)
  const plain = logic.modelAssetFromResult('m10', 'shape', { format: 'glb' })
  assert.equal(plain.texture, undefined)
  assert.equal(plain.sourceModelId, undefined)
})

console.log(`\n${passed} checks passed`)
