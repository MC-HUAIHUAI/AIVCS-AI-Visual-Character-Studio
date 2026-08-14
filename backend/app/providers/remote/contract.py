"""Provider capability contract (Phase 3-5B).

Small, deterministic capability descriptor mirroring the frontend
ProviderCapabilities. `kind` explicitly marks the provenance class:

    - "mock"     -> simulated vendor (MockRemote3DClient). Never presented as
                    a real AI result; provenance is carried by provider_id /
                    JobResult metadata (GLB bytes are NOT modified).
    - "real"     -> a future real vendor adapter (VendorXClient).
    - "skeleton" -> offline placeholder that must not run (VendorRemoteClient).

Provider identity (id) is separate from availability (enabled). A provider is
registered once; `enabled` only controls whether real generation may run.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapability:
    mode: str  # "cloud" | "local"
    gpu_required: bool
    max_references: int
    output_format: str  # "glb"
    supports_cancel: bool
    supports_timeout: bool
    kind: str  # "mock" | "real" | "skeleton"
