"""MockRemote3DProvider - RealAIImage3DProvider wired to the mock client.

Registers a "simulated vendor" through the exact same remote-task pipeline as a
real vendor, so success / failure / timeout / cancel / invalid-GLB / remote
error paths are all reachable without any real 3D API.
"""

from __future__ import annotations

from .mock_client import MockRemote3DClient
from .real_ai import RealAIImage3DProvider


class MockRemote3DProvider(RealAIImage3DProvider):
    id = "mock-remote"
    name = "Mock Remote（模拟厂商）"
    description = "模拟真实厂商的 创建任务→轮询→下载 GLB 流程，无需任何真实 3D API。"
    client: MockRemote3DClient

    def __init__(self, scenario: str = "success", **client_kwargs):
        super().__init__(
            client=MockRemote3DClient(scenario=scenario, **client_kwargs),
            provider_id="mock-remote",
            provider_name="Mock Remote（模拟厂商）",
            description="模拟真实厂商的 创建任务→轮询→下载 GLB 流程，无需任何真实 3D API。",
            default_timeout_seconds=30.0,
        )
