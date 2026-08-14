/**
 * Phase 3-5A app settings logic tests.
 * Runs against tsc-compiled CommonJS output in .review-test/ (no framework).
 */
import { createRequire } from 'node:module'
import { strict as assert } from 'node:assert'

const require = createRequire(import.meta.url)
const logic = require('../.review-test/renderer/src/core/settings/appSettingsLogic.js')

function check(name, fn) {
  try {
    fn()
    console.log(`  ok - ${name}`)
  } catch (err) {
    console.error(`  FAIL - ${name}: ${err.message}`)
    process.exitCode = 1
  }
}

check('default settings all disabled', () => {
  const s = logic.defaultAppSettings()
  assert.equal(s.version, 1)
  assert.deepEqual(s.vision, { enabled: false, providerId: '', baseUrl: '', apiKey: '' })
  assert.deepEqual(s.external3d, { enabled: false, providerId: '', baseUrl: '', apiKey: '' })
})

check('providerStatus derivation', () => {
  const u = { enabled: false, providerId: '', baseUrl: '', apiKey: '' }
  const cd = { enabled: false, providerId: 'kimi', baseUrl: 'https://api.moonshot.cn/v1', apiKey: 'sk-x' }
  const en = { enabled: true, providerId: 'kimi', baseUrl: 'https://api.moonshot.cn/v1', apiKey: 'sk-x' }
  assert.equal(logic.providerStatus(u), 'unconfigured')
  assert.equal(logic.providerStatus(cd), 'configured-disabled')
  assert.equal(logic.providerStatus(en), 'enabled')
})

check('validateAppSettings: disabled -> no issues', () => {
  const s = logic.defaultAppSettings()
  assert.deepEqual(logic.validateAppSettings(s), [])
})

check('validateAppSettings: enabled requires providerId/baseUrl/apiKey', () => {
  const s = logic.defaultAppSettings()
  s.vision = { enabled: true, providerId: '', baseUrl: '', apiKey: '' }
  const issues = logic.validateAppSettings(s)
  const visionFields = issues.filter((i) => i.section === 'vision').map((i) => i.field)
  assert.ok(visionFields.includes('providerId'))
  assert.ok(visionFields.includes('baseUrl'))
  assert.ok(visionFields.includes('apiKey'))
})

check('validateAppSettings: valid config passes', () => {
  const s = logic.defaultAppSettings()
  s.vision = { enabled: true, providerId: 'kimi', baseUrl: 'https://api.moonshot.cn/v1', apiKey: 'sk-x' }
  assert.deepEqual(logic.validateAppSettings(s), [])
})

check('isBaseUrlFormatted', () => {
  assert.equal(logic.isBaseUrlFormatted('https://a.example.com'), true)
  assert.equal(logic.isBaseUrlFormatted('http://a.example.com'), true)
  assert.equal(logic.isBaseUrlFormatted('ftp://x'), false)
  assert.equal(logic.isBaseUrlFormatted(''), false)
  assert.equal(logic.isBaseUrlFormatted('not a url'), false)
})

check('redactApiKey never exposes real key', () => {
  assert.equal(logic.redactApiKey('sk-1234567890abcdef'), 'sk***ef')
  assert.equal(logic.redactApiKey('abc'), '***')
  assert.equal(logic.redactApiKey(''), '')
})

check('sanitizeSettings masks all keys', () => {
  const s = logic.defaultAppSettings()
  s.vision.apiKey = 'sk-secret'
  s.external3d.apiKey = 'other-secret'
  const clean = logic.sanitizeSettings(s)
  assert.equal(clean.vision.apiKey, '***')
  assert.equal(clean.external3d.apiKey, '***')
})

check('apiKey never appears in sanitized output', () => {
  const s = logic.defaultAppSettings()
  s.vision.apiKey = 'sk-top-secret-value'
  const clean = logic.sanitizeSettings(s)
  const dump = JSON.stringify(clean)
  assert.ok(!dump.includes('sk-top-secret-value'))
})

check('isProviderUsable', () => {
  const ok = { enabled: true, providerId: 'kimi', baseUrl: 'https://api.moonshot.cn/v1', apiKey: 'k' }
  assert.equal(logic.isProviderUsable(ok), true)
  assert.equal(logic.isProviderUsable({ ...ok, enabled: false }), false)
  assert.equal(logic.isProviderUsable({ ...ok, apiKey: '' }), false)
  assert.equal(logic.isProviderUsable({ ...ok, baseUrl: '' }), false)
})

check('testConnectionUrl strips trailing slash', () => {
  assert.equal(logic.testConnectionUrl({ enabled: true, providerId: 'x', baseUrl: 'https://a.example.com/v1/', apiKey: 'k' }), 'https://a.example.com/v1/health')
})

check('logic is pure - no network surface', () => {
  const fs = require('node:fs')
  const code = fs.readFileSync(require.resolve('../.review-test/renderer/src/core/settings/appSettingsLogic.js'), 'utf8')
  for (const needle of ['fetch(', 'XMLHttpRequest', 'axios']) {
    assert.ok(!code.includes(needle), `unexpected network call surface: ${needle}`)
  }
})
