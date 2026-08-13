# AIVCS - AI Virtual Character Studio

面向 Windows 的 AI 虚拟主播（VTuber / 虚拟形象）制作软件。

当前版本：**0.2.1（Phase 2.2 完成）**

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

## Mock 功能（模拟，非真实实现）

- **Mock AI Provider**（前端本地 + 后端各一份）：按角色类型返回对应演示 GLB（人类→人形、非人类→兽人狐），模拟各阶段耗时与进度；无需网络、无需任何 AI API
- **Vision Mock**：本地模拟图片分析（返回确定性结果 + "Mock 模式"标记），保证无 Key 离线也可演示完整的分析→Review→采纳链路
- **自然语言编辑**：仅解析为结构化命令并展示，不实际修改模型
- **毛发**：只以样式字段 + 步骤提示表现，无真实毛发网格

## 尚未实现功能（后续 Phase）

- 真实 Image-to-3D（`RealImage3DProviderPlaceholder` 已占位，抛"未实现"）
- 真实骨骼生成与蒙皮绑定（RigProfile 数据已就绪）
- 真实毛发（贴图/法线/材质、Hair cards、Groom curves）
- VRM 导出（非人类结构作为 Extra Bones 的规则已定义）
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
