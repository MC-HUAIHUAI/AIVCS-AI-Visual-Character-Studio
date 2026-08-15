# THIRD-PARTY NOTICES

本文件记录 AIVCS 仓库内除 AIVCS 自有代码外的第三方材料与许可信息。

## AIVCS 自有代码

- AIVCS 自身源代码（`src/`, `backend/`, `tools/`, 前端逻辑、测试、Manifest、文档）基于仓库根目录 `LICENSE`（MIT License, Copyright (c) 2026 MC_HUAIHUAI）。
- 内置演示模型（`assets/demo_character.glb`, `assets/demo_fox.glb`）由 AIVCS 工具生成，随 MIT 许可分发。
- Dummy Runtime（`resources/ai/3d/runtimes/dummy/dummy_ai3d_runtime.py`）为 AIVCS 的本地测试/验证 runtime（**不是真实 AI**），属 AIVCS 自有代码，MIT。

## Hunyuan3D-2 相关（接口 / Manifest / 文档引用）

- 本仓库中与 Hunyuan3D 相关的**接口代码、Runtime manifest、文档与兼容层**仅引用官方项目 `github.com/Tencent-Hunyuan/Hunyuan3D-2` 的公开信息（`api_server.py` 的 `/send` + `/status` 协议、官方 README 的 VRAM/模型说明）。
- 这些内容**不构成对 Hunyuan 的重新分发或修改**，用户使用 Hunyuan 时须遵守其原始许可证。
- **Hunyuan 许可证**：Tencent Hunyuan Community License（非 MIT）：
  - **禁止在欧盟 / 英国 / 韩国使用或分发**；
  - **月活跃用户超过 100 万**的商用场景须向腾讯申请商业许可；
  - 详情以官方仓库 LICENSE 为准。
- **真实 Hunyuan 模型权重不会随本仓库分发**，也不在本仓库中。

## 第三方依赖

- 前端依赖由 `package.json` / `package-lock.json` 管理（npm）；后端依赖由 `backend/requirements.txt` 管理（pip）。各依赖的许可证以其包元数据为准。
- AIVCS 不 vendoring 任何第三方源码进本仓库；用户安装依赖时自行负责遵守对应许可证。

## 模型权重声明

- 本仓库**不包含**任何真实 AI 模型权重（无 `.safetensors` / `.ckpt` / `.pt` / `.onnx` 等）。
- 若用户按 manifest 自行下载 Hunyuan 权重，须遵守 Tencent Hunyuan Community License 并在使用前阅读对应 LICENSE / NOTICE。
