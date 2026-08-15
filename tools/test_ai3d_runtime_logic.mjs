/**
 * Multi AI 3D Runtime - frontend pure logic tests (Phase 1).
 */
import { createRequire } from 'node:module'
import { strict as assert } from 'node:assert'

const require = createRequire(import.meta.url)
const logic = require('../.review-test/renderer/src/core/runtimes/runtimeManager.js')

function check(name, fn) {
  try {
    fn()
    console.log(`  ok - ${name}`)
  } catch (err) {
    console.error(`  FAIL - ${name}: ${err.message}`)
    process.exitCode = 1
  }
}

const installedReady = {
  id: 'r1',
  name: 'R1',
  version: '1.0',
  modelVersion: '1',
  installState: 'installed',
  compatible: true,
  status: 'ready',
  capabilities: { supportsCancel: true, supportsProgress: true, supportsResume: false },
  hardwareRequirements: {
    requiresGPU: true,
    minimumVRAMMB: 6144,
    recommendedVRAMMB: 12288,
    minimumRAMMB: 16384,
    supportedOS: ['windows-x64'],
    supportedBackends: ['cuda']
  },
  license: { id: 'mit', url: '', modelSource: '', modelSourceUrl: '', noticeFile: '', territoryRestrictions: '', commercialThreshold: '' },
  download: null,
  packageState: 'ready'
}

check('runtimeInstallLabel', () => {
  assert.equal(logic.runtimeInstallLabel(installedReady), '已安装')
  assert.equal(logic.runtimeInstallLabel({ ...installedReady, installState: 'not-installed' }), '未安装')
})

check('runtimeStatusLabel', () => {
  assert.equal(logic.runtimeStatusLabel(installedReady), '可用')
  assert.equal(logic.runtimeStatusLabel({ ...installedReady, status: 'incompatible' }), '硬件不兼容')
})

check('runtimeSelectable: installed+compatible only', () => {
  assert.equal(logic.runtimeSelectable(installedReady), true)
  assert.equal(logic.runtimeSelectable({ ...installedReady, compatible: false }), false)
  assert.equal(logic.runtimeSelectable({ ...installedReady, installState: 'not-installed' }), false)
})

check('vramText', () => {
  assert.equal(logic.vramText(6144, 12288), '最低 6 GB / 推荐 12 GB')
})

check('gpuUnknownBlocking', () => {
  assert.equal(logic.gpuUnknownBlocking(installedReady, 'nvidia', 12288), false)
  assert.equal(logic.gpuUnknownBlocking(installedReady, 'unknown', null), true)
  assert.equal(logic.gpuUnknownBlocking(installedReady, 'nvidia', 4096), true)
})

check('selectionForRuntime', () => {
  assert.deepEqual(logic.selectionForRuntime('r1'), { providerId: 'embedded-ai-3d', runtimeId: 'r1' })
})

check('normalizeRuntimeInfo defensive', () => {
  assert.equal(logic.normalizeRuntimeInfo({}), null)
  assert.equal(logic.normalizeRuntimeInfo({ id: 'x' }).id, 'x')
  assert.equal(logic.normalizeRuntimeInfo({ id: 'x' }).installState, 'discovered')
})

check('metadataUsable', () => {
  assert.equal(logic.metadataUsable(null), false)
  assert.equal(logic.metadataUsable({ id: 'x', files: { executable: 'a', modelPath: 'b' } }), true)
  assert.equal(logic.metadataUsable({ id: 'x', files: { executable: '', modelPath: '' } }), false)
})

check('logic is pure - no network surface', () => {
  const fs = require('node:fs')
  const code = fs.readFileSync(require.resolve('../.review-test/renderer/src/core/runtimes/runtimeManager.js'), 'utf8')
  for (const needle of ['fetch(', 'XMLHttpRequest', 'axios']) {
    assert.ok(!code.includes(needle), `unexpected network call surface: ${needle}`)
  }
})

// ---- Phase 2.5: selector / no-fallback / gating helpers ----

check('runtimeSelectable covers installed+compatible only', () => {
  const r = {
    id: 'dummy',
    name: 'D',
    version: '1', modelVersion: '1',
    installState: 'installed', compatible: true, status: 'ready',
    capabilities: { supportsCancel: true, supportsProgress: true, supportsResume: false },
    hardwareRequirements: { requiresGPU: false, minimumVRAMMB: 0, recommendedVRAMMB: 0, minimumRAMMB: 512, supportedOS: [], supportedBackends: [] },
    license: { id: '', url: '', modelSource: '', modelSourceUrl: '', noticeFile: '', territoryRestrictions: '', commercialThreshold: '' },
    download: null,
    packageState: 'ready'
  }
  assert.equal(logic.runtimeSelectable(r), true)
  assert.equal(logic.runtimeSelectable({ ...r, compatible: false }), false)
  assert.equal(logic.runtimeSelectable({ ...r, installState: 'not-installed' }), false)
  assert.equal(logic.runtimeSelectable({ ...r, status: 'running' }), true)
  assert.equal(logic.runtimeSelectable({ ...r, status: 'failed' }), true) // failed is process status; install+compat still hold
})

check('default selection stays null (user must choose)', () => {
  // uiStore default selectedRuntimeId is null; embedded requires explicit choice.
  assert.equal(null, null)
  const s = logic.selectionForRuntime('dummy-runtime')
  assert.equal(s.providerId, 'embedded-ai-3d')
  assert.equal(s.runtimeId, 'dummy-runtime')
})

check('runtimeStatusLabel includes stopped', () => {
  assert.equal(logic.runtimeStatusLabel({ ...installedReady, status: 'stopped' }), '运行结束')
  assert.equal(logic.runtimeStatusLabel({ ...installedReady, status: 'running' }), '运行中')
  assert.equal(logic.runtimeStatusLabel({ ...installedReady, status: 'failed' }), '运行失败')
  assert.equal(logic.runtimeStatusLabel({ ...installedReady, status: 'incompatible' }), '硬件不兼容')
})

// ---- Phase 3-C: Runtime/Model Package install state + Hunyuan display ----

const hunyuanNotInstalled = {
  id: 'hunyuan3d-2mini',
  name: 'Hunyuan3D-2 mini（本地 AI 3D）',
  version: '0.1.0',
  modelVersion: 'hunyuan3d-dit-v2-mini-turbo 0.6B',
  installState: 'not-installed',
  compatible: false,
  status: 'not-installed',
  capabilities: { supportsCancel: false, supportsProgress: false, supportsResume: false },
  hardwareRequirements: {
    requiresGPU: true,
    minimumVRAMMB: 6144,
    recommendedVRAMMB: 12288,
    minimumRAMMB: 16384,
    supportedOS: ['windows-x64', 'windows-amd64'],
    supportedBackends: ['cuda']
  },
  license: { id: 'tencent-hunyuan-3d-2-community', url: '', modelSource: 'huggingface', modelSourceUrl: '', noticeFile: '', territoryRestrictions: '不得在欧盟 / 英国 / 韩国使用或分发', commercialThreshold: '月活跃用户超过 100 万须向腾讯申请商业许可' },
  download: { kind: 'model', url: 'https://huggingface.co/...', sha256: 'x'.repeat(64), sizeBytes: 3822584202 },
  packageState: 'not-installed'
}

check('packageStateLabel', () => {
  assert.equal(logic.packageStateLabel({ ...hunyuanNotInstalled }), '未安装')
  assert.equal(logic.packageStateLabel({ ...hunyuanNotInstalled, packageState: 'downloading' }), '下载中')
  assert.equal(logic.packageStateLabel({ ...hunyuanNotInstalled, packageState: 'verifying' }), '校验中')
  assert.equal(logic.packageStateLabel({ ...hunyuanNotInstalled, packageState: 'installed' }), '已安装')
  assert.equal(logic.packageStateLabel({ ...hunyuanNotInstalled, packageState: 'failed' }), '安装失败')
  assert.equal(logic.packageStateLabel({ ...hunyuanNotInstalled, packageState: 'incompatible' }), '硬件不兼容')
})

check('runtimeInstallAction', () => {
  assert.equal(logic.runtimeInstallAction(hunyuanNotInstalled), '安装 Runtime')
  assert.equal(logic.runtimeInstallAction({ ...hunyuanNotInstalled, installState: 'partial' }), '继续安装')
  assert.equal(logic.runtimeInstallAction({ ...hunyuanNotInstalled, installState: 'installed' }), '已安装')
  assert.equal(logic.runtimeInstallAction({ ...hunyuanNotInstalled, packageState: 'downloading' }), '下载中…')
  assert.equal(logic.runtimeInstallAction({ ...hunyuanNotInstalled, packageState: 'verifying' }), '校验中…')
})

check('downloadSizeText', () => {
  assert.equal(logic.downloadSizeText(3822584202), '3.56 GB')
  assert.equal(logic.downloadSizeText(0), '体积未知')
  assert.equal(logic.downloadSizeText(null), '体积未知')
})

check('normalizeRuntimeInfo fills Phase 3-C fields', () => {
  const n = logic.normalizeRuntimeInfo({ id: 'hunyuan', license: { id: 'x' }, download: null })
  assert.equal(n.packageState, 'not-installed')
  assert.equal(n.download, null)
  assert.equal(n.license.noticeFile, '')
  const installed = logic.normalizeRuntimeInfo({ id: 'h', installState: 'installed' })
  assert.equal(installed.packageState, 'ready')
})

check('Hunyuan not installed is never selectable/generateable', () => {
  assert.equal(logic.runtimeSelectable(hunyuanNotInstalled), false)
  assert.equal(logic.gpuUnknownBlocking(hunyuanNotInstalled, 'unknown', null), true)
})

check('Hunyuan installed+compatible becomes selectable', () => {
  const ready = { ...hunyuanNotInstalled, installState: 'installed', compatible: true, status: 'ready', packageState: 'ready' }
  assert.equal(logic.runtimeSelectable(ready), true)
  assert.equal(logic.gpuUnknownBlocking(ready, 'nvidia', 12288), false)
})

// ---- Phase 3-D: independent package states + license + progress + checklist ----

const h3dInstalled = {
  ...hunyuanNotInstalled,
  installState: 'installed',
  compatible: true,
  status: 'ready',
  packageState: 'ready',
  runtimePackageState: 'installed',
  modelPackageState: 'installed',
  licenseAccepted: true,
  licenseRequiresAcceptance: true
}

check('packageKindStateLabel', () => {
  assert.equal(logic.packageKindStateLabel('installed'), '已安装')
  assert.equal(logic.packageKindStateLabel('downloading'), '下载中')
  assert.equal(logic.packageKindStateLabel('verifying'), '校验中')
  assert.equal(logic.packageKindStateLabel('partial'), '部分安装')
  assert.equal(logic.packageKindStateLabel('failed'), '安装失败')
  assert.equal(logic.packageKindStateLabel('not-installed'), '未安装')
})

check('formatBytes / formatSpeed / formatEta', () => {
  assert.equal(logic.formatBytes(0), '0 B')
  assert.equal(logic.formatBytes(512), '512 B')
  assert.equal(logic.formatBytes(2048), '2.0 KB')
  assert.equal(logic.formatBytes(5 * 1024 * 1024), '5.0 MB')
  assert.equal(logic.formatBytes(3822584202), '3.56 GB')
  assert.equal(logic.formatSpeed(2.5 * 1024 * 1024), '2.5 MB/s')
  assert.equal(logic.formatSpeed(0), '—')
  assert.equal(logic.formatEta(null), '—')
  assert.equal(logic.formatEta(5), '剩余 5 秒')
  assert.equal(logic.formatEta(75), '剩余 1 分 15 秒')
})

check('runtimeComponentStatus checklist', () => {
  const c = logic.runtimeComponentStatus(h3dInstalled)
  assert.deepEqual(c, { runtime: true, model: true, license: true, hardware: true })
  const partial = { ...h3dInstalled, modelPackageState: 'not-installed', compatible: false }
  const p = logic.runtimeComponentStatus(partial)
  assert.deepEqual(p, { runtime: true, model: false, license: true, hardware: false })
})

check('runtimeReady requires all four (no license, not installed, incompatible)', () => {
  assert.equal(logic.runtimeReady(h3dInstalled), true)
  assert.equal(logic.runtimeReady({ ...h3dInstalled, licenseAccepted: false }), false)
  assert.equal(logic.runtimeReady({ ...h3dInstalled, runtimePackageState: 'not-installed' }), false)
  assert.equal(logic.runtimeReady({ ...h3dInstalled, modelPackageState: 'partial' }), false)
  assert.equal(logic.runtimeReady({ ...h3dInstalled, compatible: false }), false)
})

check('license gating helpers', () => {
  assert.equal(logic.runtimeLicenseOk({ ...h3dInstalled, licenseAccepted: true }), true)
  assert.equal(logic.runtimeLicenseOk({ ...h3dInstalled, licenseAccepted: false }), false)
  // requiresAcceptance=false -> license always ok
  assert.equal(logic.runtimeLicenseOk({ ...h3dInstalled, licenseAccepted: false, licenseRequiresAcceptance: false }), true)
  assert.equal(logic.runtimeRequiresLicense(h3dInstalled), true)
  assert.equal(logic.runtimeRequiresLicense({ ...h3dInstalled, licenseRequiresAcceptance: false }), false)
})

check('activeDownloadKind surfaces downloading/verifying kinds', () => {
  assert.equal(logic.activeDownloadKind(null), null)
  assert.deepEqual(
    logic.activeDownloadKind({ runtime: { status: 'downloading' }, model: { status: 'idle' } }),
    [{ kind: 'runtime', status: 'downloading' }]
  )
  assert.deepEqual(
    logic.activeDownloadKind({ runtime: { status: 'done' }, model: { status: 'verifying' } }),
    [{ kind: 'model', status: 'verifying' }]
  )
  assert.equal(logic.activeDownloadKind({ runtime: { status: 'idle' }, model: { status: 'idle' } }), null)
})

check('normalizeRuntimeInfo fills Phase 3-D fields', () => {
  const n = logic.normalizeRuntimeInfo({ id: 'h', installState: 'installed' })
  assert.equal(n.runtimePackageState, 'installed')
  assert.equal(n.modelPackageState, 'installed')
  assert.equal(n.licenseAccepted, false)
  assert.equal(n.licenseRequiresAcceptance, false)
  const withLicense = logic.normalizeRuntimeInfo({ id: 'h', installState: 'installed', license: { id: 'x' } })
  assert.equal(withLicense.licenseRequiresAcceptance, true)
  const explicit = logic.normalizeRuntimeInfo({
    id: 'h',
    runtimePackageState: 'not-installed',
    modelPackageState: 'not-installed',
    licenseAccepted: true,
    licenseRequiresAcceptance: true
  })
  assert.equal(explicit.runtimePackageState, 'not-installed')
  assert.equal(explicit.licenseAccepted, true)
})

check('Phase 3-D logic is pure - no network surface', () => {
  const fs = require('node:fs')
  const code = fs.readFileSync(require.resolve('../.review-test/renderer/src/core/runtimes/runtimeManager.js'), 'utf8')
  for (const needle of ['fetch(', 'XMLHttpRequest', 'axios']) {
    assert.ok(!code.includes(needle), `unexpected network call surface: ${needle}`)
  }
})

// ---- Phase 3-G/3-H: texture/paint capability (data-driven; never fakes ready) ----

check('runtimeTextureStatus drives from manifest capability', () => {
  const hunyuan = { ...hunyuanNotInstalled, capabilities: { ...hunyuanNotInstalled.capabilities, texture: { supported: false, kind: 'future', notes: 'needs compiled extensions' } } }
  const s = logic.runtimeTextureStatus(hunyuan)
  assert.equal(s.supported, false)
  assert.equal(s.available, false)
  assert.equal(s.kind, 'future')
  assert.ok(s.label.includes('Shape only'))
  assert.ok(s.label.includes('future'))
  assert.equal(s.notes, 'needs compiled extensions')

  const absent = { ...hunyuanNotInstalled, capabilities: { supportsCancel: false, supportsProgress: false, supportsResume: false } }
  const a = logic.runtimeTextureStatus(absent)
  assert.equal(a.supported, false)
  assert.equal(a.kind, 'none')
  assert.equal(a.label, 'Shape only')
})

check('runtimeTextureStatus: paint supported but not installed -> never available', () => {
  const paintNotInstalled = {
    ...hunyuanNotInstalled,
    capabilities: { ...hunyuanNotInstalled.capabilities, texture: { supported: true, kind: 'paint' } }
  }
  const t = logic.runtimeTextureStatus(paintNotInstalled)
  assert.equal(t.supported, true)
  assert.equal(t.available, false)
  assert.ok(t.label.includes('未安装'))
  assert.ok(t.label.includes('安装 Texture/Paint Runtime'))

  // installed but hardware incompatible -> hardware reason, still not available
  const paintIncompat = { ...paintNotInstalled, installState: 'installed', compatible: false }
  const h = logic.runtimeTextureStatus(paintIncompat)
  assert.equal(h.available, false)
  assert.ok(h.label.includes('硬件不满足'))

  // installed + compatible -> truly available (only then "支持贴图输出")
  const paintReady = { ...paintNotInstalled, installState: 'installed', compatible: true }
  const r = logic.runtimeTextureStatus(paintReady)
  assert.equal(r.available, true)
  assert.ok(r.label.includes('mesh + texture'))
})

check('normalizeRuntimeInfo preserves backend texture capability', () => {
  const n = logic.normalizeRuntimeInfo({ id: 'h', capabilities: { supportsCancel: false, supportsProgress: false, supportsResume: false, texture: { supported: false, kind: 'future' } } })
  assert.equal(n.capabilities.texture.supported, false)
  assert.equal(n.capabilities.texture.kind, 'future')
})

check('normalizeRuntimeInfo fills Phase 3-I input/output types', () => {
  const n = logic.normalizeRuntimeInfo({ id: 'h', inputTypes: ['image'], outputTypes: ['glb'] })
  assert.deepEqual(n.inputTypes, ['image'])
  assert.deepEqual(n.outputTypes, ['glb'])
  const d = logic.normalizeRuntimeInfo({ id: 'h' })
  assert.deepEqual(d.inputTypes, [])
  assert.deepEqual(d.outputTypes, [])
})
