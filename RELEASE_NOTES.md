# AIVCS 0.3.0 — Local AI 3D Runtime Foundation

发布说明（对应当前工作树状态；尚未发布 tag）。

## Highlights

- **Embedded AI 3D Runtime Manager**：manifest 驱动的本地 AI 3D Runtime 发现 / 独立 Runtime+Model 包安装 / 状态机 / 生命周期管理。
- **Runtime installer**：HTTPS 默认 + SHA-256/size 校验 + `.part` 原子替换 + host-redirect 防护 + License 接受门禁 + Hardware 门禁 + 下载取消/失败恢复。
- **Dummy Runtime E2E**：本地 HTTP 测试 runtime 验证 创建→轮询→取消→下载→GLB→ModelStore→Renderer 全链路（非真实 AI）。
- **Hunyuan3D-2mini Runtime 集成**：官方 `/send`+`/status` 协议适配；shape 权重校验码记录于 manifest；硬件/许可门禁完整。
- **GLB → VRM pipeline**：analyze → human/non-human 判定 →（复用骨骼或确定性 auto-rig）→ skin weights / bind pose / bone mapping → VRM 1.0 导出 + 校验；非人体明确拒绝。
- **Texture metadata pipeline**：texture capability / metadata 在 ModelStore → API → Renderer 全链一致；Paint 保持 future/unavailable 不伪装。
- **Hardware compatibility detection**：NVIDIA/AMD/Intel/unknown + DXGI 检测；未知不伪造；仅 NVIDIA 提供 cuda。
- **Crash recovery / token rotation / port allocation**：Runtime 崩溃可重启，token 每次轮换，端口释放复用。
- **Windows packaged resource support**：packaged 版本随包携带 AI 3D manifests + Dummy Runtime，下载落 `userData/ai/3d`。

## 重要声明

- **真实 Hunyuan Shape/Paint 推理尚未在本机（无 NVIDIA GPU）验证**。当前构建环境无 NVIDIA，真实 GPU 端到端验证属于后续 Phase 4，**不要将 Dummy/测试 GLB 成功 Rig 误认为 Hunyuan 已成功**。
- 默认 provider 为 `mock-local`，无需任何 AI 模型即可运行。
- 本仓库不含任何真实模型权重；Hunyuan 权重需用户按官方来源与许可证自行获取。
