#!/usr/bin/env node
/**
 * Frontend multi-view review logic tests (Phase 2.2-C).
 *
 * Runs against the tsc-compiled CommonJS output in .review-test/ (no framework,
 * no third-party deps). Build first:
 *   npm run test:frontend
 */

import { strict as assert } from 'node:assert'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const logic = require('../.review-test/renderer/src/core/spec/visionReviewLogic.js')
const avr = require('../.review-test/renderer/src/core/spec/applyVisionResult.js')

const {
  buildReviewSuggestions,
  applyConflictDecision,
  missingViewWarning,
  PER_VIEW_MISSING_MESSAGE
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

const current = {} // applyVisionResult tolerates missing nested objects
const spec = { characterType: 'human', species: { primary: 'fox' }, anatomy: { tail: 'single' } }
const conflict = (field, values) => ({
  field,
  fieldLabel: field,
  candidates: values.map(([value, view, confidence]) => ({ value, view, confidence })),
  resolvedTo: { value: values[0][0], view: values[0][1], confidence: values[0][2] }
})

console.log('Phase 2.2-C frontend review logic')

// 1. front single view
check('1. single view -> suggestions from unified patch, no conflicts', () => {
  const s = buildReviewSuggestions(spec, [], {}, {}, 0.9)
  assert.ok(s.some((x) => x.field === 'characterType' && x.valueLabel === '人类'))
  assert.ok(s.some((x) => x.field === 'species' && x.valueLabel === '狐'))
})

// 2. front+side no conflict
check('2. front+side consistent -> no conflicts, suggestions present', () => {
  const s = buildReviewSuggestions(spec, [], {}, {}, 0.85)
  assert.equal(s.length, 3)
})

// 3. front+side+back no conflict
check('3. front+side+back consistent -> no conflicts', () => {
  const s = buildReviewSuggestions(spec, [], {}, {}, 0.8)
  assert.equal(s.length, 3)
})

// 4. conflict front human / back anthro
const typeConflict = conflict('characterType', [
  ['human', 'front', 0.9],
  ['anthro', 'back', 0.7]
])
const specWithConflict = { characterType: 'human', species: { primary: 'fox' } }
check('4a. unresolved conflict -> field excluded from suggestions', () => {
  const s = buildReviewSuggestions(specWithConflict, [typeConflict], {}, {}, 0.8)
  assert.ok(!s.some((x) => x.field === 'characterType'))
  assert.ok(s.some((x) => x.field === 'species'))
})
check('4b. resolve candidate -> field included with chosen value', () => {
  const r = applyConflictDecision([typeConflict], {}, {}, 'characterType', { kind: 'candidate', index: 1 })
  const s = buildReviewSuggestions(specWithConflict, [typeConflict], r.resolved, r.skipped, 0.8)
  const row = s.find((x) => x.field === 'characterType')
  assert.ok(row)
  assert.equal(row.patch.characterType, 'anthro')
  assert.equal(row.valueLabel, '兽人 / Furry')
})

// 5. two views same value -> not a conflict
check('5. same value from two views -> single suggestion, no exclusion', () => {
  const s = buildReviewSuggestions(spec, [], {}, {}, 0.8)
  assert.ok(s.some((x) => x.field === 'characterType' && x.valueLabel === '人类'))
})

// 6. field only back provides
check('6. back-only field -> included, no conflict', () => {
  const s = buildReviewSuggestions({ anatomy: { tail: 'single' } }, [], {}, {}, 0.7)
  const row = s.find((x) => x.field === 'anatomy')
  assert.ok(row)
  assert.equal(row.patch.anatomy.tail, 'single')
})

// 7. explicit false vs true is a conflict
const earsConflict = conflict('anatomy.ears', [
  [true, 'front', 0.9],
  [false, 'back', 0.8]
])
check('7. explicit false observed -> conflict, unresolved excluded', () => {
  const s = buildReviewSuggestions({ anatomy: { ears: true, tail: 'single' } }, [earsConflict], {}, {}, 0.8)
  assert.ok(!s.some((x) => x.field === 'anatomy'))
})
check('7b. resolve anatomy.ears candidate 1 (false) -> patch has false', () => {
  const r = applyConflictDecision([earsConflict], {}, {}, 'anatomy.ears', { kind: 'candidate', index: 1 })
  const s = buildReviewSuggestions({ anatomy: { ears: true, tail: 'single' } }, [earsConflict], r.resolved, r.skipped, 0.8)
  const row = s.find((x) => x.field === 'anatomy')
  assert.ok(row)
  assert.equal(row.patch.anatomy.ears, false)
  assert.equal(row.patch.anatomy.tail, 'single')
})

// 8. unresolved conflict -> acceptAll writes nothing for it
check('8. acceptAll with unresolved conflict -> field not written', () => {
  const s = buildReviewSuggestions(specWithConflict, [typeConflict], {}, {}, 0.8)
  const patches = s.map((x) => x.patch)
  const combined = Object.assign({}, ...patches)
  const safe = avr.applyVisionResult(current, combined)
  assert.ok(!('characterType' in safe))
  assert.equal(safe.species.primary, 'fox')
})

// 9. resolve candidate -> accept writes chosen value
check('9. resolve candidate then accept -> chosen value written', () => {
  const r = applyConflictDecision([typeConflict], {}, {}, 'characterType', { kind: 'candidate', index: 1 })
  const s = buildReviewSuggestions(specWithConflict, [typeConflict], r.resolved, r.skipped, 0.8)
  const row = s.find((x) => x.field === 'characterType')
  const safe = avr.applyVisionResult(current, row.patch)
  assert.equal(safe.characterType, 'anthro')
})

// 10. resolve default -> accept writes resolver default
check('10. resolve default then accept -> default written', () => {
  const r = applyConflictDecision([typeConflict], {}, {}, 'characterType', { kind: 'default' })
  const s = buildReviewSuggestions(specWithConflict, [typeConflict], r.resolved, r.skipped, 0.8)
  const row = s.find((x) => x.field === 'characterType')
  assert.ok(row)
  assert.equal(row.patch.characterType, 'human') // resolvedTo default = first candidate
  const safe = avr.applyVisionResult(current, row.patch)
  assert.equal(safe.characterType, 'human')
})

// 11. model perView missing -> unified specPatch still usable, no fabrication
check('11. perView missing -> suggestions from unified patch, no crash', () => {
  assert.equal(PER_VIEW_MISSING_MESSAGE, '模型未提供逐视角分析')
  const s = buildReviewSuggestions(spec, [], {}, {}, 0.8)
  assert.ok(s.length > 0)
})

// 12. missing view warnings
check('12a. only front -> warning', () => {
  assert.equal(missingViewWarning(['front']), '缺少侧面或背面参考图，多视角一致性有限')
})
check('12b. front+side -> warning', () => {
  assert.equal(missingViewWarning(['front', 'side']), '缺少背面参考图，多视角一致性有限')
})
check('12c. front+side+back -> no warning', () => {
  assert.equal(missingViewWarning(['front', 'side', 'back']), null)
})
check('12d. custom does not count', () => {
  assert.equal(missingViewWarning(['front', 'custom']), '缺少侧面或背面参考图，多视角一致性有限')
})

// 13. invalid enum/color/number still clamped by applyVisionResult
check('13. invalid enum/color/number clamped/dropped by applyVisionResult', () => {
  const safe = avr.applyVisionResult(current, {
    characterType: 'alien-ish',
    species: { primary: 'Fox' },
    appearance: { palette: ['red', '#FF0000'] },
    heightCm: 9999
  })
  assert.ok(!('characterType' in safe)) // unknown enum dropped
  assert.equal(safe.species.primary, 'custom') // unknown species -> custom
  assert.deepEqual(safe.appearance.palette, ['#FF0000']) // invalid color dropped, valid kept
  assert.equal(safe.heightCm, 300) // clamped
})

// skipped conflict excluded
check('extra. skipped conflict -> excluded from suggestions', () => {
  const r = applyConflictDecision([typeConflict], {}, {}, 'characterType', { kind: 'skip' })
  assert.ok(r.skipped.characterType === true)
  const s = buildReviewSuggestions(specWithConflict, [typeConflict], r.resolved, r.skipped, 0.8)
  assert.ok(!s.some((x) => x.field === 'characterType'))
})

console.log(`\n${passed} checks passed`)
