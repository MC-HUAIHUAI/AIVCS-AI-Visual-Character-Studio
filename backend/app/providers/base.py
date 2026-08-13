"""AI image-to-3D provider abstraction (backend).

The frontend talks to this through its own AIImage3DProvider HTTP client; the
backend holds the real provider registry so real vendors can be added without
touching the UI.

Phase 2.3-A contract: providers receive the unified CharacterSpec, the reference
images (VisionImageInput, max 4), a progress callback and a cooperative
CancellationToken. Timeout/cancel/failure are handled by the JobManager.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ..schemas.character import CharacterSpec
from ..schemas.vision import VisionImageInput

ProgressCallback = Callable[[int, int, str], None]
# (step_index, total_steps, message)


class CancellationToken:
    """Cooperative cancellation flag shared with the running job."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


class AIImage3DProvider(ABC):
    """Base contract every backend image-to-3D provider implements."""

    id: str = "base"
    name: str = "Base"
    description: str = ""

    @abstractmethod
    async def generate(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        on_progress: ProgressCallback,
        cancel_event: CancellationToken | None = None,
    ) -> bytes:
        """Run the pipeline and return the raw GLB bytes.

        Implementations should poll `cancel_event.is_cancelled` between steps and
        raise ProviderCancelledError when the user cancels the job.
        """
        raise NotImplementedError


class ProviderError(RuntimeError):
    """Raised by providers when generation fails."""


class ProviderCancelledError(ProviderError):
    """Raised by providers when the job was cancelled mid-generation."""
