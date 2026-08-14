/**
 * Phase 3-4 2D layered portrait logic tests.
 * Runs against tsc-compiled CommonJS output in .review-test/ (no framework).
 */
import { createRequire } from 'node:module'
import { strict as assert } from 'node:assert'

const require = createRequire(import.meta.url)
const logic = require('../.review-test/renderer/src/core/spec/portrait2dLogic.js')

function check(name, fn) {
  try {
    fn()
    console.log(`  ok - ${name}`)
  } catch (err) {
    console.error(`  FAIL - ${name}: ${err.message}`)
    process.exitCode = 1
  }
}

function spec(bodyType = 'humanoid', name = '测试角色', anatomyOverrides = {}) {
  return {
    id: 's',
    name,
    style: 'stylized',
    gender: 'female',
    heightCm: 160,
    description: '',
    referenceImageIds: [],
    tags: [],
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    characterType: 'human',
    species: { primary: 'custom', secondary: null, confidence: null, label: null },
    bodyType,
    anatomy: {
      hasHead: true,
      hasFace: true,
      hasTorso: true,
      hasLimbs: true,
      tail: 'none',
      wings: false,
      ears: false,
      horns: false,
      antlers: false,
      snout: false,
      muzzle: false,
      beak: false,
      paws: false,
      claws: false,
      hooves: false,
      fins: false,
      tentacles: false,
      extraLimbs: false,
      customAppendages: [],
      ...anatomyOverrides
    },
    fur: { enabled: false, style: 'none', length: 'medium', colors: [], patterns: [] },
    appearance: { baseColor: null, secondaryColors: [], patterns: [], markings: [], palette: [] },
    visionAnalysis: null,
    userNotes: null
  }
}

function asset(overrides = {}) {
  return {
    version: 1,
    palette: [],
    baseColor: null,
    secondaryColors: [],
    furColors: [],
    furPatterns: [],
    hairColor: null,
    eyeColor: null,
    skinColor: null,
    outfitColors: [],
    backPattern: null,
    source: {},
    ...overrides
  }
}

// 1. humanoid full portrait, all 6 layers, correct order
check('1. humanoid -> ok, 6 layers in fixed order', () => {
  const out = logic.buildPortrait2D(spec(), asset())
  assert.equal(out.status, 'ok')
  const ids = out.result.descriptor.layers.map((l) => l.id)
  assert.deepEqual(ids, ['body', 'outfit', 'face', 'eyes', 'hair', 'accessory'])
})

// 2. skin/eye/hair/outfit drive correct layers
check('2. colors propagate to correct layers', () => {
  const out = logic.buildPortrait2D(spec(), asset({
    skinColor: '#A0522D', hairColor: '#FFD700', eyeColor: '#00BFFF',
    outfitColors: ['#FF4500', '#228B22', '#FF00FF']
  }))
  const byId = Object.fromEntries(out.result.descriptor.layers.map((l) => [l.id, l.svg]))
  assert.ok(byId.face.includes('#A0522D'))
  assert.ok(byId.hair.includes('#FFD700'))
  assert.ok(byId.eyes.includes('#00BFFF'))
  assert.ok(byId.outfit.includes('#FF4500'))
})

// 3. different asset -> SVG DIFFER
check('3. different asset -> SVG DIFFER', () => {
  const a = logic.buildPortrait2D(spec(), asset({ eyeColor: '#111111' })).result.svg
  const b = logic.buildPortrait2D(spec(), asset({ eyeColor: '#222222' })).result.svg
  assert.notEqual(a, b)
})

// 4. same input -> identical SVG
check('4. same input -> identical SVG', () => {
  const s = spec()
  const a = logic.buildPortrait2D(s, asset({ skinColor: '#A0522D', hairColor: '#FFD700' })).result.svg
  const b = logic.buildPortrait2D(s, asset({ skinColor: '#A0522D', hairColor: '#FFD700' })).result.svg
  assert.equal(a, b)
})

// 5. no asset -> deterministic default
check('5. no asset -> deterministic default', () => {
  const s = spec()
  const a = logic.buildPortrait2D(s).result.svg
  const b = logic.buildPortrait2D(s, null).result.svg
  assert.equal(a, b)
  assert.ok(a.includes('<svg'))
})

// 6. biped-anthro keeps appendages when anatomy says so
check('6. biped-anthro appendages kept (ears/tail/horns/wings)', () => {
  const out = logic.buildPortrait2D(
    spec('biped-anthro', '兽人', { ears: true, horns: true, tail: 'single', wings: true }),
    asset({ hairColor: '#884422', outfitColors: ['#445566'] })
  )
  const acc = out.result.descriptor.layers.find((l) => l.id === 'accessory').svg
  assert.ok(acc.includes('Q120 40')) // ear path
  assert.ok(acc.includes('Q138 22')) // horn path
  assert.ok(acc.includes('Q150 530')) // tail path
  assert.ok(acc.includes('Q40 220')) // wing path
})

// 7. biped-anthro without appendage info -> no accessory invented
check('7. biped-anthro no anatomy -> no accessory guessed', () => {
  const out = logic.buildPortrait2D(spec('biped-anthro'), asset())
  const layers = out.result.descriptor.layers
  assert.ok(!layers.some((l) => l.id === 'accessory' && l.svg !== ''))
})

// 8. custom not forced into full humanoid
check('8. custom -> partial, only reliable layers', () => {
  const out = logic.buildPortrait2D(spec('custom', '异形', { hasLimbs: false, tail: 'none', ears: false }), asset())
  const ids = out.result.descriptor.layers.map((l) => l.id)
  assert.ok(ids.includes('body') && ids.includes('outfit'))
  assert.ok(ids.includes('face') && ids.includes('eyes'))
  // no hair (no hairColor) and no accessory
  assert.ok(!ids.includes('hair'))
  assert.ok(!ids.includes('accessory'))
})

// 9. unsupported body types
check('9. quadruped/bird/dragon/robot -> unsupported', () => {
  for (const bt of ['quadruped', 'bird', 'dragon', 'robot']) {
    const out = logic.buildPortrait2D(spec(bt), asset())
    assert.equal(out.status, 'unsupported', bt)
    assert.equal(out.bodyType, bt)
    assert.match(out.reason, /不映射成人形模板/)
  }
})

// 10. SVG validity
check('10. SVG is well-formed skeleton', () => {
  const out = logic.buildPortrait2D(spec(), asset())
  assert.ok(out.result.svg.startsWith('<svg'))
  assert.ok(out.result.svg.endsWith('</svg>'))
  // every <path ...> is either self-closing (<path .../>) or closed (</path>)
  const open = (out.result.svg.match(/<path\b/g) || []).length
  const selfClosed = (out.result.svg.match(/<path\b[^>]*\/>/g) || []).length
  const closed = (out.result.svg.match(/<\/path>/g) || []).length
  assert.equal(open, selfClosed + closed)
  assert.ok(out.result.svg.includes('xmlns="http://www.w3.org/2000/svg"'))
})

// 11. descriptor completeness
check('11. descriptor complete and honest', () => {
  const out = logic.buildPortrait2D(spec(), asset({ backPattern: '背部白色条纹' }))
  const d = out.result.descriptor
  assert.equal(d.version, 1)
  assert.equal(d.kind, '2d-layered')
  assert.equal(d.note, '2D layered / Live2D-ready，非 Cubism Runtime，不含 physics/parameter/motion')
  assert.equal(d.width, 400)
  assert.equal(d.height, 600)
  assert.equal(d.frontView, true)
  assert.equal(d.backPattern, '背部白色条纹')
  assert.equal(d.cubism.present, false)
  assert.deepEqual(d.cubism.parameters, {
    headYaw: '',
    headPitch: '',
    eyeOpen: '',
    mouthOpen: '',
    bodySway: ''
  })
  assert.ok(Array.isArray(d.layers) && d.layers.length > 0)
})

// 12. backPattern metadata only - not fabricated as texture
check('12. backPattern is metadata, never drawn as texture', () => {
  const out = logic.buildPortrait2D(spec(), asset({ backPattern: '背部白色条纹' }))
  assert.equal(out.result.descriptor.backPattern, '背部白色条纹')
  assert.ok(!out.result.svg.includes('背部'))
})

// 13. filename / mime
check('13. filename and mime', () => {
  const out = logic.buildPortrait2D(spec('humanoid', '狐狸龙'), asset())
  assert.equal(out.result.fileName, '狐狸龙.svg')
  assert.equal(out.result.mime, 'image/svg+xml')
  const empty = logic.buildPortrait2D(spec('humanoid', '   '), asset())
  assert.equal(empty.result.fileName, 'AIVCS Character.svg')
})

// 14. layer order by field
check('14. layer order ascending', () => {
  const out = logic.buildPortrait2D(spec(), asset())
  const orders = out.result.descriptor.layers.map((l) => l.order)
  for (let i = 1; i < orders.length; i++) assert.ok(orders[i] > orders[i - 1])
})

// 15. provenance sources preserved
check('15. provenance sources recorded', () => {
  const out = logic.buildPortrait2D(spec(), asset({ hairColor: '#FFD700', source: { hairColor: 'observed' } }))
  const hair = out.result.descriptor.layers.find((l) => l.id === 'hair')
  assert.equal(hair.sources.hair, 'observed')
})

// 16. pure - no network surface
check('16. logic is pure - no network surface', () => {
  const fs = require('node:fs')
  const code = fs.readFileSync(require.resolve('../.review-test/renderer/src/core/spec/portrait2dLogic.js'), 'utf8')
  for (const needle of ['fetch(', 'XMLHttpRequest', 'axios']) {
    assert.ok(!code.includes(needle), `unexpected network call surface: ${needle}`)
  }
})

// ---- Phase 3-4.5: metadata (anchors / parameters / appendages) ----

// 17. SVG golden: byte-identical to Phase 3-4
check('17. SVG golden identical to Phase 3-4', () => {
  const crypto = require('node:crypto')
  // humanoid - same inputs as the Phase 3-4 golden capture.
  const h = logic.buildPortrait2D(spec(), asset({ hairColor: '#FFD700', eyeColor: '#00BFFF', skinColor: '#E8CDB3', outfitColors: ['#FF4500', '#228B22'] }))
  const hSha = crypto.createHash('sha256').update(h.result.svg).digest('hex')
  assert.equal(hSha, 'd045e3608eb281210aa1e9c2055578f01c9b3e584c70b15fb2da4ca2707ef0de')
  assert.equal(h.result.svg.length, 514)
  // biped-anthro with appendages
  const a = logic.buildPortrait2D(
    spec('biped-anthro', '兽', { ears: true, horns: true, tail: 'single', wings: true }),
    asset({ hairColor: '#884422', eyeColor: '#00BFFF', skinColor: '#E8CDB3', outfitColors: ['#445566'], backPattern: '白背纹' })
  )
  const aSha = crypto.createHash('sha256').update(a.result.svg).digest('hex')
  assert.equal(aSha, '8e1c63e4e2771f1d009dbcad2f67ca384c5abbc7d0cf2cd546b36dc7f69e8764')
  assert.equal(a.result.svg.length, 1030)
})

// 18. five parameters exist with range/default and binds
check('18. five parameters, range [-1,1], default 0, binds correct', () => {
  const out = logic.buildPortrait2D(spec(), asset())
  const params = out.result.descriptor.parameters
  assert.ok(Array.isArray(params) && params.length === 5)
  const byId = Object.fromEntries(params.map((p) => [p.id, p]))
  for (const id of ['headYaw', 'headPitch', 'eyeOpen', 'mouthOpen', 'bodySway']) {
    assert.ok(byId[id], `missing ${id}`)
    assert.deepEqual(byId[id].range, [-1, 1])
    assert.equal(byId[id].default, 0)
  }
  assert.deepEqual(byId.headYaw.binds, ['face', 'hair', 'eyes', 'accessory'])
  assert.deepEqual(byId.headPitch.binds, ['face', 'hair', 'eyes'])
  assert.deepEqual(byId.eyeOpen.binds, ['eyes'])
  assert.deepEqual(byId.mouthOpen.binds, ['face'])
  assert.deepEqual(byId.bodySway.binds, ['body', 'outfit'])
})

// 19. layer anchors deterministic metadata
check('19. layer anchors deterministic', () => {
  const s = spec()
  const a = logic.buildPortrait2D(s, asset()).result.descriptor.layers.map((l) => l.anchor)
  const b = logic.buildPortrait2D(s, asset()).result.descriptor.layers.map((l) => l.anchor)
  assert.deepEqual(a, b)
  const face = logic.buildPortrait2D(s, asset()).result.descriptor.layers.find((l) => l.id === 'face')
  assert.deepEqual(face.anchor, { x: 200, y: 150 })
})

// 20. appendages only when anatomy present, individually listed
check('20. appendages per anatomy, not guessed', () => {
  const none = logic.buildPortrait2D(spec('biped-anthro'), asset())
  assert.deepEqual(none.result.descriptor.appendages, [])
  const withAnatomy = logic.buildPortrait2D(
    spec('biped-anthro', '兽', { ears: true, horns: true, tail: 'single', wings: true }),
    asset()
  )
  const ids = withAnatomy.result.descriptor.appendages.map((ap) => ap.id).sort()
  assert.deepEqual(ids, ['ears_L', 'ears_R', 'horn_L', 'horn_R', 'tail', 'wing_L', 'wing_R'])
  // all live in accessory layer
  assert.ok(withAnatomy.result.descriptor.appendages.every((ap) => ap.layer === 'accessory'))
})

// 21. mouthOpen declared but no fabricated mouth in SVG
check('21. mouthOpen declared, no mouth fabricated', () => {
  const out = logic.buildPortrait2D(spec(), asset())
  const mouth = out.result.descriptor.parameters.find((p) => p.id === 'mouthOpen')
  assert.ok(mouth)
  assert.ok(!out.result.svg.includes('mouth'))
})

// 22. cubism.present false, parameters empty
check('22. cubism.present=false, parameters empty', () => {
  const out = logic.buildPortrait2D(spec(), asset())
  assert.equal(out.result.descriptor.cubism.present, false)
  const params = out.result.descriptor.cubism.parameters
  assert.deepEqual(Object.keys(params).sort(), ['bodySway', 'eyeOpen', 'headPitch', 'headYaw', 'mouthOpen'])
  assert.ok(Object.values(params).every((v) => v === ''))
})
