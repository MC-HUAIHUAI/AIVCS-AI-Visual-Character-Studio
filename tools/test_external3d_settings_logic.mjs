/**
 * Phase 2.4-D-pre external 3D provider settings logic tests.
 * Runs against tsc-compiled CommonJS output in .review-test/ (no framework).
 */
import { createRequire } from 'node:module'
import { strict as assert } from 'node:assert'

const require = createRequire(import.meta.url)
const logic = require('../.review-test/renderer/src/core/settings/external3dSettingsLogic.js')

function check(name, fn) {
  try {
    fn()
    console.log(`  ok - ${name}`)
  } catch (err) {
    console.error(`  FAIL - ${name}: ${err.message}`)
    process.exitCode = 1
  }
}

check('default settings are disabled', () => {
  const d = logic.DEFAULT_EXTERNAL3D_SETTINGS
  assert.deepEqual(d, { enabled: false, providerId: '', baseUrl: '', apiKey: '' })
})

check('isExternal3DReserved is true in this release', () => {
  assert.equal(logic.isExternal3DReserved(), true)
})

check('reserved notice text', () => {
  assert.equal(logic.external3DReservedNotice(), '外部 3D Provider：已预留配置（真实服务尚未实现）')
  assert.equal(logic.external3DDisabledReason(), '真实外部 3D 服务尚未实现，仅可配置；当前版本继续使用本地 LocalLowPower / Mock。')
})

check('baseUrl format check accepts http/https', () => {
  assert.equal(logic.isBaseUrlFormatted('https://example.com/v1'), true)
  assert.equal(logic.isBaseUrlFormatted('http://example.com'), true)
})

check('baseUrl format check rejects non-http / junk', () => {
  assert.equal(logic.isBaseUrlFormatted(''), false)
  assert.equal(logic.isBaseUrlFormatted('ftp://example.com'), false)
  assert.equal(logic.isBaseUrlFormatted('not a url'), false)
  assert.equal(logic.isBaseUrlFormatted('example.com'), false)
})

check('validation returns no issues while disabled', () => {
  const issues = logic.validateExternal3DSettings(logic.DEFAULT_EXTERNAL3D_SETTINGS)
  assert.deepEqual(issues, [])
})

check('validation flags empty providerId / bad baseUrl / missing key when enabled', () => {
  const issues = logic.validateExternal3DSettings({ enabled: true, providerId: '', baseUrl: '', apiKey: '' })
  assert.equal(issues.length, 3)
  assert.ok(issues.some((i) => i.field === 'providerId'))
  assert.ok(issues.some((i) => i.field === 'baseUrl'))
  assert.ok(issues.some((i) => i.field === 'apiKey'))
})

check('validation passes with formatted values + key', () => {
  const issues = logic.validateExternal3DSettings({ enabled: true, providerId: 'external-3d', baseUrl: 'https://api.example.com', apiKey: 'sk-test' })
  assert.deepEqual(issues, [])
})

check('providerStatus derivation', () => {
  assert.equal(logic.providerStatus({ enabled: false, providerId: '', baseUrl: '', apiKey: '' }), 'unconfigured')
  assert.equal(logic.providerStatus({ enabled: false, providerId: 'x', baseUrl: 'https://a', apiKey: 'k' }), 'configured-disabled')
  assert.equal(logic.providerStatus({ enabled: true, providerId: 'x', baseUrl: 'https://a', apiKey: 'k' }), 'enabled')
})

check('redactApiKey hides real key', () => {
  assert.equal(logic.redactApiKey('abcdef123456'), 'ab***56')
  assert.equal(logic.redactApiKey(''), '')
  assert.equal(logic.redactApiKey('abcdef'), '***')
})

check('logic is pure - no network surface', () => {
  const src = require.resolve('../.review-test/renderer/src/core/settings/external3dSettingsLogic.js')
  const fs = require('node:fs')
  const code = fs.readFileSync(src, 'utf8')
  for (const needle of ['fetch(', 'XMLHttpRequest', 'axios', 'http.']) {
    assert.ok(!code.includes(needle), `unexpected network call surface: ${needle}`)
  }
})
