/**
 * Phase 3-1 CharacterAsset logic tests.
 * Runs against tsc-compiled CommonJS output in .review-test/ (no framework).
 */
import { createRequire } from 'node:module'
import { strict as assert } from 'node:assert'

const require = createRequire(import.meta.url)
const logic = require('../.review-test/renderer/src/core/spec/characterAssetLogic.js')

function check(name, fn) {
  try {
    fn()
    console.log(`  ok - ${name}`)
  } catch (err) {
    console.error(`  FAIL - ${name}: ${err.message}`)
    process.exitCode = 1
  }
}

const spec = {
  appearance: { baseColor: '#123456', secondaryColors: ['#AABBCC'], palette: ['#FF0000', '#00FF00'] },
  fur: { enabled: true, colors: ['#111111'], patterns: ['条纹'] }
}

check('derive from spec: palette derived', () => {
  const a = logic.deriveCharacterAsset(spec)
  assert.deepEqual(a.palette, ['#FF0000', '#00FF00'])
  assert.equal(a.source.palette, 'derived')
  assert.equal(a.source.baseColor, 'derived')
  assert.deepEqual(a.outfitColors, ['#FF0000', '#00FF00', undefined].slice(0, 2))
})

check('derive: absent fields stay none', () => {
  const a = logic.deriveCharacterAsset(spec)
  assert.equal(a.hairColor, null)
  assert.equal(a.eyeColor, null)
  assert.equal(a.skinColor, null)
  assert.equal(a.source.hairColor, undefined)
  assert.equal(a.source.eyeColor, undefined)
  assert.equal(a.backPattern, null)
})

check('derive: deterministic', () => {
  const a = logic.deriveCharacterAsset(spec)
  const b = logic.deriveCharacterAsset(spec)
  assert.deepEqual(a, b)
})

check('derive: empty spec no crash, all none', () => {
  const a = logic.deriveCharacterAsset({ appearance: {}, fur: {} })
  assert.deepEqual(a.palette, [])
  assert.deepEqual(a.outfitColors, [])
  assert.deepEqual(a.source, {})
})

check('applyAssetPatch marks observed', () => {
  const base = logic.deriveCharacterAsset(spec)
  const merged = logic.applyAssetPatch(base, {
    hairColor: '#111222',
    eyeColor: '#333444',
    skinColor: '#E8CDB3',
    outfitColors: ['#FF0000', '#00FF00', '#0000FF'],
    backPattern: '背部白色条纹'
  })
  assert.equal(merged.hairColor, '#111222')
  assert.equal(merged.source.hairColor, 'observed')
  assert.equal(merged.eyeColor, '#333444')
  assert.equal(merged.skinColor, '#E8CDB3')
  assert.deepEqual(merged.outfitColors, ['#FF0000', '#00FF00', '#0000FF'])
  assert.equal(merged.backPattern, '背部白色条纹')
  assert.equal(merged.source.backPattern, 'observed')
})

check('applyAssetPatch clamps invalid colors', () => {
  const base = logic.deriveCharacterAsset(spec)
  const merged = logic.applyAssetPatch(base, { hairColor: 'not-a-color', outfitColors: ['red', '#00AA00'] })
  assert.equal(merged.hairColor, null)
  assert.deepEqual(merged.outfitColors, ['#00AA00'])
})

check('hasObservableAssetPatch', () => {
  assert.equal(logic.hasObservableAssetPatch(null), false)
  assert.equal(logic.hasObservableAssetPatch({}), false)
  assert.equal(logic.hasObservableAssetPatch({ hairColor: '#111222' }), true)
  assert.equal(logic.hasObservableAssetPatch({ outfitColors: [] }), false)
  assert.equal(logic.hasObservableAssetPatch({ outfitColors: ['#111222'] }), true)
})

check('logic is pure - no network surface', () => {
  const fs = require('node:fs')
  const code = fs.readFileSync(require.resolve('../.review-test/renderer/src/core/spec/characterAssetLogic.js'), 'utf8')
  for (const needle of ['fetch(', 'XMLHttpRequest', 'axios']) {
    assert.ok(!code.includes(needle), `unexpected network call surface: ${needle}`)
  }
})
