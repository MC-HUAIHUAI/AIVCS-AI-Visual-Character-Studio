# AIVCS - AI Virtual Character Studio

面向 Windows 的 AI 虚拟主播（VTuber / 虚拟形象）制作软件。

当前版本：**0.1.0（Phase 1 完成）**

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

## Mock 功能（模拟，非真实实现）

- **Mock AI Provider**（前端本地 + 后端各一份）：按角色类型返回对应演示 GLB（人类→人形、非人类→兽人狐），模拟各阶段耗时与进度；无需网络、无需任何 AI API
- **物种识别**：不真正分析图片；当物种置信度为空时明确提示"无法确定角色物种，请选择或补充参考图"
- **自然语言编辑**：仅解析为结构化命令并展示，不实际修改模型
- **毛发**：只以样式字段 + 步骤提示表现，无真实毛发网格

## 尚未实现功能（后续 Phase）

- 真实 Image-to-3D（`RealImage3DProviderPlaceholder` 已占位，抛"未实现"）
- 真实物种 / 外观识别（AI 分析参考图）
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
