/**
 * Phase 2.7-D VRM export logic tests.
 * Runs against tsc-compiled CommonJS output in .review-test/ (no framework).
 */
import { createRequire } from 'node:module'
import { strict as assert } from 'node:assert'

const require = createRequire(import.meta.url)
const logic = require('../.review-test/renderer/src/core/spec/vrmExportLogic.js')

function check(name, fn) {
  try {
    fn()
    console.log(`  ok - ${name}`)
  } catch (err) {
    console.error(`  FAIL - ${name}: ${err.message}`)
    process.exitCode = 1
  }
}

const backendModel = {
  id: 'model-1',
  name: '角色',
  source: 'generated',
  format: 'glb',
  providerId: 'backend-local-lowpower',
  filePath: null,
  addedAt: ''
}
const demoModel = { id: 'demo-character', name: '演示', source: 'demo', format: 'glb', filePath: null, addedAt: '' }
const localMockModel = { id: 'model-x', name: '本地', source: 'generated', format: 'glb', providerId: 'mock-local', filePath: null, addedAt: '' }

check('backend model + online -> can export', () => {
  assert.equal(logic.canExportVrm(backendModel, true), true)
})

check('backend offline -> cannot export', () => {
  assert.equal(logic.canExportVrm(backendModel, false), false)
})

check('null model -> cannot export', () => {
  assert.equal(logic.canExportVrm(null, true), false)
})

check('demo model (no backend record) -> cannot export', () => {
  assert.equal(logic.canExportVrm(demoModel, true), false)
})

check('local mock model (no backend record) -> cannot export', () => {
  assert.equal(logic.canExportVrm(localMockModel, true), false)
})

check('skinned=false -> cannot export', () => {
  assert.equal(logic.canExportVrm({ ...backendModel, glbStats: { skinned: false } }, true), false)
})

check('skinned=true -> can export', () => {
  assert.equal(logic.canExportVrm({ ...backendModel, glbStats: { skinned: true } }, true), true)
})

check('skinned missing (old project) -> allowed (backend decides)', () => {
  assert.equal(logic.canExportVrm({ ...backendModel }, true), true)
})

check('isBackendModel true for backend providers', () => {
  for (const id of ['backend-fastapi', 'backend-local-lowpower', 'backend-mock-remote']) {
    assert.equal(logic.isBackendModel({ ...backendModel, providerId: id }), true)
  }
})

check('vrmFileName uses spec name with .vrm', () => {
  assert.equal(logic.vrmFileName('狐狸龙'), '狐狸龙.vrm')
})

check('vrmFileName sanitizes illegal chars', () => {
  assert.equal(logic.vrmFileName('a/b:c*v?'), 'a_b_c_v_.vrm')
})

check('vrmFileName falls back when empty', () => {
  assert.equal(logic.vrmFileName('   '), 'AIVCS Character.vrm')
})

check('body_type whitelist mirrors backend', () => {
  assert.deepEqual(Array.from(logic.VRM_EXPORTABLE_BODY_TYPES).sort(), ['biped-anthro', 'custom', 'humanoid'])
})

check('vrmErrorText network offline', () => {
  assert.match(logic.vrmErrorText(null, null, true), /后端离线/)
  assert.match(logic.vrmErrorText(0, null, true), /后端离线/)
})

check('vrmErrorText 404 model not found', () => {
  assert.match(logic.vrmErrorText(404, null, false), /模型不存在/)
})

check('vrmErrorText 400 surfaces backend detail verbatim', () => {
  assert.equal(logic.vrmErrorText(400, 'bodyType \'quadruped\' 无法导出', false), 'bodyType \'quadruped\' 无法导出')
})

check('vrmErrorText 400 empty detail -> generic', () => {
  assert.match(logic.vrmErrorText(400, null, false), /后端拒绝/)
})

check('vrmErrorText other status', () => {
  assert.match(logic.vrmErrorText(500, null, false), /HTTP 500/)
})

check('logic is pure - no network surface', () => {
  const fs = require('node:fs')
  const code = fs.readFileSync(require.resolve('../.review-test/renderer/src/core/spec/vrmExportLogic.js'), 'utf8')
  for (const needle of ['fetch(', 'XMLHttpRequest', 'axios']) {
    assert.ok(!code.includes(needle), `unexpected network call surface: ${needle}`)
  }
})
