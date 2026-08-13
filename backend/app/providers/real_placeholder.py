"""Placeholder for a real image-to-3D vendor.

A future provider (e.g. Trellis, Meshy, TripoSR) would read its API key from
the environment here - never from code - and stream the same GLB bytes back
through the AIImage3DProvider contract.
"""

from __future__ import annotations

from .base import AIImage3DProvider, CancellationToken, ProgressCallback, ProviderError
from ..schemas.character import CharacterSpec
from ..schemas.vision import VisionImageInput


class RealImage3DProviderPlaceholder(AIImage3DProvider):
    """Not implemented. Reserved slot to prove the provider seam is open."""

    id = "real-placeholder"
    name = "Real AI (placeholder)"
    description = "A real image-to-3D vendor will live here. Not implemented in Phase 1."

    async def generate(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        on_progress: ProgressCallback,
        cancel_event: CancellationToken | None = None,
    ) -> bytes:
        raise ProviderError(
            "The real image-to-3D provider is not implemented yet. Use the Mock provider in Demo Mode."
        )
