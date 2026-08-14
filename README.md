# AIVCS - AI Virtual Character Studio

面向 Windows 的 AI 虚拟主播（VTuber / 虚拟形象）制作软件。

当前版本：**0.2.2（Phase 2.3 完成）**

## 技术栈

- Electron 33 + React 18 + TypeScript（strict）
- Vite / electron-vite（构建与开发服务器）
- Three.js（3D 视口）
- Zustand（状态管理）
- Python 3.12+ / FastAPI（本地后端）
- 无任何外部 AI API 依赖，Demo Mode 开箱即用

## 开发环境

- Node.js ≥ 20（本项目在 v24 上验证）
- npm ≥ 10
- Python ≥ 3.10（本项目在 3.14 上验证）
- Windows（优先目标平台）

## 安装

```bash
npm install
npm run backend:install   # 安装 FastAPI 后端依赖（pip install -r backend/requirements.txt）
python tools/gen_demo_character.py   # 重新生成演示角色 GLB（如需）
```

> 提示：若 Electron 二进制下载超时，可设置镜像后重装：
> `$env:ELECTRON_MIRROR='https://npmmirror.com/mirrors/electron/'`

## 启动

```bash
# 终端 1：FastAPI 后端（端口 8321）
npm run backend

# 终端 2：Electron 应用（开发模式，自动打开窗口）
npm run dev
```

其他脚本：

| 脚本 | 说明 |
| --- | --- |
| `npm run typecheck` | TypeScript 严格类型检查（node + web） |
| `npm run build` | 生产构建（输出到 `out/`） |
| `npm run preview` | 预览生产构建 |
| `npm run backend` | 启动 FastAPI 后端 |
| `npm run backend:install` | 安装后端依赖 |
| `npm run gen:demo` | 重新生成演示角色 GLB |

## API 配置（可选）

AIVCS 默认无需任何 API Key 即可运行：无 API 时使用本地 Mock / LocalLowPower / 2D 功能，**启动零外部网络请求**。

第三方 API（Vision / External 3D）由**最终用户**在软件 **设置（Settings）** 中自行配置：

- 打开 **设置** → **Vision Provider** / **External 3D Provider**
- 填写 Provider / Base URL / API Key，勾选启用
- 点击 **测试连接**（仅在你主动点击时才产生网络请求）
- API Key 仅加密保存在本机（Electron safeStorage），**绝不进入项目文件 / 导出数据 / 日志**

**优先级规则**：

```
用户 Settings 中配置并启用 → 使用用户配置（source = runtime）
用户未配置 → 使用本地 Mock / 本地能力
```

- 发行版**不依赖**开发者的 `.env` 文件。
- `.env` / 环境变量（如 `AIVCS_KIMI_API_KEY`）**仅作为开发者本地 fallback**，且仅在用户未在 Settings 中配置时生效——用户填写自己的 Key 后绝不会使用开发者的 Key。
- 无任何 API Key 时：正常启动、创建项目、使用本地/Mock 3D、使用 2D 立绘。

## 已实现功能（Phase 1）

- **桌面应用**：Electron + React + TypeScript（strict）深色专业 UI，界面全中文
- **布局**：顶部标题栏（新建/打开/保存/导出 GLB/后端状态）、左侧素材库、中央 3D 视口、右侧 AI 助手、底部生成进度
- **项目管理**：创建 / 保存 / 加载（`.aivcsproj.json`），旧版本项目自动兼容补全
- **素材导入**：PNG / JPG / WEBP 参考图导入与管理（缩略图、尺寸、移除）
- **3D 视口**：Three.js 加载 GLB，支持旋转（左键）/缩放（滚轮）/平移（右键），前/后/左/右/顶/透视六种相机预设，自动取景
- **演示角色**：两个内置演示模型（人类 Q 版 + 兽人狐），从底层证明非人类管线可用
- **AI Provider 抽象**：TypeScript 接口 + Python ABC 双端抽象，Mock 与未来真实提供方可随时替换
- **Character Specification**：结构化角色规格（名称/风格/性别/身高/描述/角色类型/物种/解剖图/毛发/配色），前后端字段一致
- **非人类 / Furry 支持**：角色类型（人类/二次元/兽人/动物/奇幻生物/机器人/外星/自定义）、物种、体型（RigProfile 骨骼模板：人类/四足/兽人/鸟/龙/自定义）、尾巴/耳朵/角/翼等可选特征部件、毛发样式
- **生成流程**：模拟 image-to-3D 管线，进度面板实时显示步骤（随角色类型动态生成）；完成后模型自动载入视口并加入素材库
- **自然语言编辑**：Mock 解释器把自然语言指令（如"把尾巴变得更蓬松"）转换为结构化 `CharacterEditCommand`
- **GLB/GLTF 导出**：从视口导出当前模型（GLB 可用；GLTF/L2D/VRM 为接口预留）

## 已实现功能（Phase 2.1 — Vision 分析基础 + 真实 Kimi）

- **Vision Provider 抽象**：前端 `AIVisionProvider`（TS）+ 后端 `AIVisionProvider`（Python ABC），与 Image-to-3D Provider 完全对称
- **Vision Mock 全链路**：参考图 → Mock 分析 → Review 建议列表 → 用户逐条确认 → `applyVisionResult` → CharacterSpec（离线可演示，无任何 API）
- **Review / 采纳流程**：`VisionAnalysisPanel` + `SpecReviewList`；AI 仅提供建议，未采纳的字段绝不写入 CharacterSpec；采纳后经枚举 clamp + 数值 clamp + `normalizeSpec` 合并
- **真实 Kimi Vision**：`backend/app/providers/vision/kimi.py` 接入 Moonshot Kimi（模型 `kimi-k2.6`），OpenAI 兼容 `/chat/completions` + `image_url`（data URL）+ `response_format: json_object`；输出经 `vision_spec_mapper` 归一（枚举白名单、未知→custom、物种不确定→confidence null、palette 仅 `#RRGGBB`）
- **安全边界**：`sourceImageIds` 由服务端从请求生成（不信任模型）；`AIVCS_KIMI_API_KEY` 仅后端环境变量 / `backend/.env`，前端/项目文件/IPC 零接触；未配置 Key 时自动回退 Mock，后端照常启动
- **错误处理**：401/403、429、5xx、超时、响应非 JSON、无 choices、空内容均映射为用户安全的中文提示（502/503），UI 不崩溃
- **schema 一致性**：`npm run check:schema` 校验 TS ↔ Pydantic 11 组模型字段一致

## 已实现功能（Phase 2.2 — 多视角 Vision + Cross-view 一致性 + 冲突解决）

- **多视角联合分析（Joint）**：最多 4 张参考图（front/side/back/custom）在一次 Kimi 请求中发送，每张带视角标签；`analysisMode='joint'` 为默认，`per-view` 仅 schema 预留、未实现逐图请求（router 显式拒绝）
- **CrossViewResolver**（`backend/app/services/cross_view_resolver.py`）：确定性、无 LLM、无网络；统一结果与冲突检测的唯一事实来源；枚举/布尔/数值（身高容差）冲突规则、缺失≠false、逐视角归一后合并；11 项单测
- **每视角分析（perView）**：模型输出逐视角观察 → `vision_spec_mapper` 逐视角归一（非法项丢弃）→ resolver 合并；`sourceImageIds` 由服务端按 `request.references` 重绑定，不信任模型
- **冲突 Review / Resolve UI**：`ConflictResolveList` 展示冲突候选（视角/值/置信度）、采用候选 / 采用默认 / 跳过；未解决或跳过的冲突**绝不写入 CharacterSpec**；解决后进入普通 Review 建议（`applyVisionResult` 是唯一写入入口）
- **多视角前端**：`VisionAnalysisPanel` 显示已选参考图与视角标签（可切换），展示顺序=冲突待解决→普通 AI 建议→每视角摘要；`perView` 缺失时显示"模型未提供逐视角分析"且不伪造
- **缺失视角提示**：仅 front / front+side 时给出 UI 警告（不进 CharacterSpec）
- **测试**：`npm run test:backend`（20）+ `npm run test:frontend`（19，纯逻辑，无新依赖）

## 已实现功能（Phase 2.3 — Image-to-3D 任务管线 + 本地低功耗 3D 原型）

- **3D Job 状态机**（`backend/app/jobs.py`）：`queued → running → done | failed | timed_out | cancelled`（queued 亦可直接 cancelled/timed_out）；`deadline + asyncio.wait_for` 超时→`timed_out`、用户取消→`cancelled`、Provider 异常→`failed(retryable)`；`timed_out` 与 `failed`、`cancelled` 与 `timed_out` 均为不同终态；**不自动重试**
- **取消/超时 API**：`POST /api/v1/generate/jobs/{id}/cancel`；请求可传 `timeoutSeconds`；Provider 契约新增 `CancellationToken`（协作式取消，步骤间检查，抛 `ProviderCancelledError`）
- **持久化 ModelStore**（`backend/app/services/model_store.py`）：`backend/data/models/{id}.glb` + 轻量 JSON sidecar；原子写入（临时文件 + rename）；`specHash`（sha256 确定性、不含 Key）；TTL 清理（`AIVCS_MODEL_TTL_HOURS`，默认 24h，注入 now/旧 mtime 可测）；重启后模型仍可读取；`GET /models/{id}/meta` 提供安全元数据
- **前端对齐**：`generationStore` 完整状态机 + `cancelJob`/`retryJob`（重试=全新 Job ID，旧 Job 保留）+ 轮询仅到终态；ProgressPanel 显示排队/生成中/完成/失败/超时/已取消 + [取消]/[重试]；`ModelAsset` 增加 providerId/sourceJobId/sizeBytes/mime（来自 JobResult，不猜测）
- **Provider 能力描述**：`AIImage3DProvider`（双端）增加 `gpu_required / max_references / output_format / supports_cancel / supports_timeout / backendId`；前端 `ProviderCapabilities`
- **LocalLowPower3DProvider**（`backend/app/providers/local_lowpower.py`，id=`local-lowpower`）：
  - **定位**：CPU 本地、确定性、低功耗的 image-to-3D 原型；证明"CharacterSpec + 多视角参考图 → 合法 GLB"的完整链路；可作为 Mock 到云端真实 3D 之间的中间档
  - **能力**：无需 GPU、无大型模型、无网络/云端 API、无 Key；内置最小 PNG 解码器提取参考图主色调（失败回退 `appearance.palette → fur.colors → spec hash` 确定性色）；按 bodyType（humanoid / biped-anthro / quadruped / bird / dragon / robot / 回退）与 anatomy 布尔（耳/尾/翼/角/吻部）生成低模拓扑，高度按 `heightCm` 缩放
  - **限制**：低模简化造型（box/sphere 组合），非高质量网格；参考图仅用于取色，不做形状重建；不确定性的艺术质量
  - **使用**：后端自动注册；前端 Provider 选择「本地低功耗 3D（CPU）」；经现有 JobManager（cancel/timeout）+ ModelStore 落盘；输出 GLB 已验证可被 three.js 加载
- **测试**：`npm run test:backend`（64：状态机/取消/超时/ModelStore/GLB 结构/低功耗 Provider/旧请求兼容）+ `npm run test:frontend`（19+17，纯逻辑）

## Phase 2.4 — 真实厂商接入层（当前状态）

- **厂商无关远程适配器**：`IRemote3DClient` 契约（create/poll/cancel/download）+ `RealAIImage3DProvider`（统一远程状态 `queued→running→done|failed|timed_out|cancelled` → JobManager 终态映射；下载→`validate_glb`→ModelStore）。
- **取消语义（Phase 2.4-B 修复）**：用户取消时先 best-effort 调用 `client.cancel_task`（最多一次，失败不掩盖取消），再转 `cancelled`。
- **超时语义**：`poll_task` 有明确 asyncio 超时边界；请求未传 `timeoutSeconds` 时后端采用安全默认（`AIVCS_GENERATION_DEFAULT_TIMEOUT_SECONDS`，默认 600s）；显式值恒优先。
- **GLB 校验**：`validate_glb` 将任何结构异常（含 JSON/accessor 越界）统一转为 `ValueError` → 安全 `ProviderError`（job failed），不扩展为完整解析器。
- **mock-remote（模拟厂商）**：完全离线、确定性，覆盖 成功/失败/超时/取消/非法 GLB/创建错误/下载失败/未知状态；经 generationStore + JobManager + ModelStore 全链路可用。
- **真实厂商：尚未启用**。`backend/app/providers/remote/vendor.py` 为离线骨架——从环境变量读 Key（`AIVCS_REAL3D_API_KEY`，预留）、无默认真实 endpoint、未配置 Key 绝不注册、不发任何网络请求。接入真实厂商只需实现 `IRemote3DClient`，**不需要**改动 JobManager / ModelStore / generationStore。
- **当前禁止自动联网**：无真实厂商配置时不发起任何远程 3D 请求；需厂商 API Key 且经授权后才能真实调用。

## Phase 2.4-C — Tripo 适配离线骨架（当前状态）

- **第一适配目标：Tripo（tripo3d.ai）**。选择理由：CN 可访问、基于 Trellis 的 image-to-3D、任务式 API（create→poll→download）与 `IRemote3DClient` 天然契合。
- **预计输入/输出**：输入=统一 CharacterSpec + references[](≤4, dataUrl)；输出=合法 GLB（下载后经 `validate_glb` 校验，再交 ModelStore）。
- **价格模型：未确认，不猜测**。需按 Tripo 官方文档核实后才能在启用真实调用前补录。
- **API Key 环境变量**：`AIVCS_TRIPO_API_KEY`（预留，见 `backend/.env.example`）。未配置绝不注册/绝不联网。
- **当前实现**：
  - `backend/app/providers/remote/tripo_client.py` — 离线骨架：DTO（结构化占位，字段需官方文档确认）、纯映射函数（`map_tripo_status` / `tripo_task_to_remote_task` / `tripo_error_to_provider_error`）、方法 `NotImplementedError`（零网络、无默认 endpoint 自动调用）。
  - `backend/app/providers/remote/offline_fake_client.py` — `OfflineFakeVendorClient`：完整离线假厂商（success / failed / timeout / cancelled / invalid / rate_limit / 用户取消），产出合法 GLB。
  - 厂商差异全部封装在 client 内；**不修改** JobManager / ModelStore / CharacterSpec / generationStore。
- **真实调用仍需人工授权**：本阶段及此前所有阶段均零真实 API、零联网、零充值。

## Phase 2.4-D-pre — Tripo 契约核对：**未能完成（官方文档不可达）**

- **核对结果：UNVERIFIED**。2026-08-14 起官方 Tripo 文档域名（`platform.tripo3d.ai` / `api-docs.tripo3d.ai` / `docs.tripo3d.ai` / `www.tripo3d.ai`）在构建环境全部无法访问，因此**未将任何 endpoint / DTO / 状态字符串声称已确认**。
- 遵守"不伪造 / 不猜"原则：未虚构官方契约细节。`tripo_client.py` 已明确标注 UNVERIFIED，方法仍为离线骨架（`NotImplementedError`，零网络）。
- **已完成的离线设计（纯函数、可测、不依赖契约）**：
  - `refs_to_tripo_input(references)`：将 `CharacterSpec.references[]` 映射为 Tripo 任务载荷的形状（每图一个 data URL + view 标签；≥2 图 → `multiview_to_model`，单图 → `image_to_model`）。
  - `multiview_suitability(views)`：判定 front/side/back 是否可直接用于 Tripo Multiview —— **结论（设计层面）：Phase 2.2 的 front/side/back 与 Tripo Multiview 天然 1:1 对应**；custom 仅作附加视角；单视角回退 `image_to_model`。
  - 状态映射 / 错误映射 / `OfflineFakeVendorClient` 全流程不变。
- **后续**：需官方文档可访问后，再按真实契约确认 endpoint/DTO/状态并启用真实适配；真实调用仍需人工授权。

## Phase 2.5 — GLB 资产分析 / 元数据 / 视口信息（当前状态）

- **GLB Asset Analyzer**（`backend/app/services/glb_analyzer.py`）：纯 stdlib、确定性；输出 `GlbStats`（mesh/primitive/vertex/index/triangle/material/texture、hasNormals/hasUVs、bounds/dimensions/center、meshStats、warnings）；以 `validate_glb` 为结构门禁（语义未改）；单个 mesh/字段异常容错（跳过 + warning，不崩溃）。
- **资产链路**：`GLB bytes → validate_glb → glb_analyzer → ModelStore(stats) → JobResult.stats → /models/{id}/meta → ModelAsset.glbStats → AssetsPanel / Viewport HUD`。stats 全部 optional，兼容任意 Provider、旧 sidecar / 旧 JobResult / 旧项目。
- **ModelStore**：`ModelRecord.stats?` + `normalizations?`（sidecar 兼容、TTL 不受影响）；生成成功自动分析，Analyzer 异常安全降级（job 保持 done，仅日志）。
- **Viewport HUD**：加载成功后显示「视口尺寸」（world Box3，`getModelInfo` 纯读取）；（有 stats 时）网格数；切换/失败即清空。
- **AssetsPanel 诊断**：选中模型显示 文件大小 / GLB 版本 / 网格 / Primitive / 顶点 / 三角形 / 材质 / 贴图 / 法线 / UV / 「GLB 分析尺寸（局部坐标）」/ Bounds / warnings；缺失字段显示「—」，不猜测。
- **当前 bounds 语义（明确区分）**：`glb_analyzer.bounds` = **POSITION accessor 局部坐标**（未应用节点变换）；`ViewportManager Box3` = **加载后的 world/scene 空间**。两者不得当作同一尺寸（UI 已分别标注「GLB 分析尺寸（局部坐标）」与「视口尺寸」）。
- **normalizations**：当前无实际生产者，保持为空、不伪造；仅当未来非空时才显示。
- **明确不做（Phase 2.5）**：GLB 重写、坐标/单位转换、Y-up 自动翻转、Rig / Skinning / VRM。
- **明确记录**：Phase 2.5 **不需要真实 3D API，也未发生任何真实 API 请求**（零联网、零 Key、零充值）。

## Phase 2.6 — Rig / Skinned GLB（当前状态）

- **RigBuilder**（`backend/app/services/rig_builder.py` + `rig_profiles.py`）：CharacterSpec → `BoneNode[]`（父子 / T-pose / heightCm 缩放 / anatomy 附加骨骼：ear/horn/antler/wing/tail 单/多链；确定性；custom 回退 humanoid）。
- **Skinned GLB**（`glb_builder.build_glb(..., bones=)`）：父子节点层级 + `skins`（joints + **bind-pose world 逆矩阵** inverseBindMatrices）+ 每顶点 `JOINTS_0`(VEC4/UINT8) / `WEIGHTS_0`(VEC4/float)；绑定在 **model space** 完成、**不改 POSITION**；无 bones 时输出**字节级不变**。
- **LocalLowPower 可选 Rig**：`AIVCS_LOCAL3D_RIG_ENABLED`（默认 **false**）开启后输出 SkinnedMesh GLB；默认保持旧非蒙皮行为字节稳定。
- **验证**：`tools/check_skinned_glb.cjs` 作为 **Three.js SkinnedMesh 硬门槛**（SkinnedMesh>0、skeleton.bones>0、skinIndex/skinWeight、bounds 非空、bones==skins.joints）；已通过 humanoid/quadruped + Job→ModelStore 管线。
- **兼容**：ModelStore / glb_analyzer / 既有 Job 管线在开关两种模式下均正常；`validate_glb` 门禁语义未改。
- **明确不做（Phase 2.6）**：动画、物理、VRM（Phase 2.7）；真实厂商接入。
- **明确记录**：Phase 2.6 纯本地实现，**未发生任何真实 API 请求**（零联网、零 Key、零充值）。

## Phase 2.7 — VRM 1.0 导出（当前状态）

- **VRM 1.0 exporter**（`backend/app/services/vrm_exporter.py` + `vrm_mapping.py`）：把 Phase 2.6 的 skinned GLB 导出为合法 VRM 1.0 GLB。基于**官方 VRM 1.0 schema**（`VRMC_vrm`/`meta`/`humanoid`/`humanBones` 必填字段与 15 个 required bones 逐一核对）；注入 `VRMC_vrm`（specVersion/meta/humanoid），保持 nodes/POSITION/skin/JOINTS_0/WEIGHTS_0/IBM 不变，仅追加合成骨骼的 bind-pose world 逆 IBM。确定性输出。
- **Required bones 合成**：把单段肢体骨拆分为 VRM 需要的 `leftLowerArm/rightLowerArm/leftLowerLeg/rightLowerLeg`；biped-anthro 缺独立手/脚时，以对应肢体骨骼自身世界位置为端点合成 `leftHand/rightHand/leftFoot/rightFoot`（确定性、无调参）。
- **白名单**：`humanoid / biped-anthro / custom` 可导出；`quadruped / bird / dragon` 明确 400（不强行映射非人类）。
- **`meta.licenseUrl`**：按官方规范使用 VRM Public License 唯一 URL `https://vrm.dev/licenses/1.0/`。
- **验证**：
  - `backend/app/services/vrm_validator.py`：零依赖结构校验（GLB 合法 / extensionsUsed / specVersion / meta required / 15 required bones node 合法 / node/joint/IBM/JOINTS_0 一致性）。
  - `tools/check_vrm.cjs`：**@pixiv/three-vrm 真实 loader 硬门槛**（devDependency 3.5.5，peer `three >= 0.137` 兼容 three@0.170）——VRM 加载 / humanoid 存在 / 15 required bones 全部可解析 / SkinnedMesh+skeleton / bounds 非空 / 可重复加载。
  - `tools/check_skinned_glb.cjs`：three.js SkinnedMesh 门槛对 .vrm 同样通过。
- **非人类 appendages**：biped-anthro 的 tail/ears/wings/horns 仍作为普通 glTF nodes/joints 存在，**不伪装成 VRM Humanoid bones**。
- **前端「导出 VRM」**（Phase 2.7-D）：TitleBar 按钮调用本地后端 `GET /api/v1/models/{id}/vrm`（`body_type`=spec.bodyType 原样透传、`name`=spec.name），复用现有保存对话框按 `.vrm` 落盘；`GlbStats.skinned`（可选字段）驱动按钮可用性，`skinned=false` 时禁用、缺失时交后端 400 明确提示；demo/本地 mock（无后端 ModelRecord）不可导出。不伪造可用状态。
- **兼容**：默认 `AIVCS_LOCAL3D_RIG_ENABLED=false` 时旧 GLB 行为与字节稳定不受影响；GlbStats.skinned 为可选字段，旧 stats/旧项目兼容；无 bones 输入安全失败。
- **明确不做（Phase 2.7）**：SpringBone / Animation / MToon / VRM 0.x / 非人类（quadruped/bird/dragon）VRM 语义 / hips 重根（规范未强制）/ 真实厂商。
- **明确记录**：Phase 2.7 纯本地实现，**未发生任何真实 API 请求**（零联网、零 Key、零充值；仅按官方 schema 文档核对字段）。

## Mock 功能（模拟，非真实实现）

- **Mock AI Provider**（前端本地 + 后端各一份）：按角色类型返回对应演示 GLB（人类→人形、非人类→兽人狐），模拟各阶段耗时与进度；无需网络、无需任何 AI API
- **Vision Mock**：本地模拟图片分析（返回确定性结果 + "Mock 模式"标记），保证无 Key 离线也可演示完整的分析→Review→采纳链路
- **自然语言编辑**：仅解析为结构化命令并展示，不实际修改模型
- **毛发**：只以样式字段 + 步骤提示表现，无真实毛发网格

## 尚未实现功能（后续 Phase）

- 真实云端 Image-to-3D（`RealImage3DProviderPlaceholder` 已占位；`LocalLowPower3DProvider` 为本地 CPU 原型，非云端质量）
- 真实骨骼生成与蒙皮绑定（RigProfile 数据已就绪）
- 真实毛发（贴图/法线/材质、Hair cards、Groom curves）
- VRM 高级能力：SpringBone / Animation / MToon / VRM 0.x；非人类（quadruped/bird/dragon）VRM 语义
- Live2D 导出 / 完整 Live2D 支持
- 动画、物理、VTuber 面部/动作追踪

## 目录结构

```
├── src/shared/         前后端共享契约（IPC 通道 + 全部数据结构）
├── src/main/           Electron 主进程（窗口、IPC 文件对话框、导出写入）
├── src/preload/        contextBridge 桥接
├── src/renderer/src/
│   ├── components/     界面组件
│   ├── core/           领域逻辑（demo 资产 / 项目 / providers / 导出器）
│   ├── store/          Zustand 状态
│   ├── three/          3D 视口管理
│   └── styles/
├── backend/app/        FastAPI 后端（providers / jobs / routers / schemas）
├── tools/              演示角色 GLB 生成器（纯 Python 标准库）
└── assets/             生成的演示模型（demo_character.glb / demo_fox.glb）
```

## 说明与限制

- 后端端口固定为 **8321**（避免与常见 8000 端口冲突）。如端口被占用可修改 `package.json` 中 `backend` 脚本与 `src/renderer/src/core/providers/httpProvider.ts` 的 `AIVCS_BACKEND_URL`。
- 生成模型为运行时内存缓存，不随项目文件持久化；重新打开项目后需重新生成。
- Phase 1 刻意不接入任何付费 AI API，API Key 零硬编码。

## Kimi Vision 接入说明（Phase 2.1 / 2.2）

- 配置：在 `backend/.env`（git 忽略，模板见 `backend/.env.example`）填入 `AIVCS_KIMI_API_KEY`；可选 `AIVCS_KIMI_BASE_URL`（默认 `https://api.moonshot.cn/v1`）、`AIVCS_KIMI_MODEL`（默认 `kimi-k2.6`）、`AIVCS_KIMI_TIMEOUT_SECONDS`（默认 240）。
- 未配置 Key 时：Vision 后端自动回退 Mock，`provider='kimi'` 返回 503；`provider='auto'` 有 Key 走 Kimi、无 Key 走 Mock。前端无需感知。
- **官方能力确认**：`kimi-k2.6` 原生支持图片输入（`content` 数组 + `image_url`，data URL，图片数量不限）、多图输入，并支持 `response_format: {"type": "json_object"}`（Vision 支持 JSON Mode）。
- **temperature 限制**：`kimi-k2.6` 的 `temperature` 不可修改（思考 1.0 / 非思考 0.6），因此不发送 temperature 参数。
- **thinking 关闭（关键修复）**：`kimi-k2.6` 思考默认开启，其 `reasoning_content` 与 `content` **共享 `max_tokens` 预算**；多视角请求思考过长时会把 `content` 挤空。因此请求显式发送 `"thinking": {"type": "disabled"}` 且 `max_tokens=8000`。修复后真实测试确认 `finish_reason=stop`、无 `reasoning_content`、`content` 非空。
- **限速与延迟现象（实测）**：当前账号 **Tier0：concurrency=1、RPM=3**，超出返回 429。真实图片分析单次耗时约 **25–35 秒**。批量测试需以 ≥25 秒间隔逐步调用，严禁自动重试；如需更高吞吐请在 Moonshot 平台提升。
- **真实 Smoke Test 结果（Phase 2.2-D，3 次请求）**：
  - T1 front+side：200 / stop / 无 reasoning / content 非空。
  - T2 front+side+back：200 / stop / content 非空；`perView=3`（views 与输入一致，服务端绑定 sourceImageIds）；resolver 检出 7 项冲突并给出统一 patch。
  - T3 front+back：200 / stop / content 非空；`perView=2`；resolver 检出 5 项冲突（人物不同视角产生差异，鲁棒性正常处理）。
- **已知限制：模型输出契约未稳定满足**——`perView[]` 在本次 2/2 返回，但早期（2.2-B.1）曾出现不返回 `perView` 的情况；`unified specPatch` 稳定。若 `perView` 缺失，管线走 Phase 2.2-C 的 fallback（不伪造、不崩溃），`conflicts` 使用后端 resolver 的真实返回。
- 测试图（6 张像素风）：人类/兽人狐/猫/龙/机器人识别正确；模糊图正确返回低置信度与"无法确定角色物种"警告。
