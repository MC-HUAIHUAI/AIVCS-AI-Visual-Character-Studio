"""Vision provider abstraction (backend).

A real image understanding provider (e.g. DeepSeek) will implement
AIVisionProvider in a later stage. Phase 2.1 only registers the Mock.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ...schemas.vision import VisionImageInput

VisionProgressCallback = Callable[[float], None]
# (progress 0..1)


class AIVisionProvider(ABC):
    """Base contract every vision analysis provider implements."""

    id: str = "base"
    display_name: str = "Base"
    requires_backend: bool = False
    description: str = ""

    @abstractmethod
    async def analyze(
        self,
        inputs: list[VisionImageInput],
        on_progress: VisionProgressCallback,
    ) -> dict:
        """Run analysis and return a raw provider result dict.

        The dict shape follows VisionProviderResult (spec_patch, confidence,
        notes, warnings, source_image_ids, provider_id). It is normalized by
        vision_spec_mapper before being returned to the client.
        """
        raise NotImplementedError


class VisionProviderError(RuntimeError):
    """Raised by providers when analysis fails."""
