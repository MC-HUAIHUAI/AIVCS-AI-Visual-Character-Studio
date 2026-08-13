"""AI image-to-3D provider abstraction (backend).

The frontend talks to this through its own AIImage3DProvider HTTP client; the
backend holds the real provider registry so real vendors can be added without
touching the UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ..schemas.character import CharacterSpec

ProgressCallback = Callable[[int, int, str], None]
# (step_index, total_steps, message)


class AIImage3DProvider(ABC):
    """Base contract every backend image-to-3D provider implements."""

    id: str = "base"
    name: str = "Base"
    description: str = ""

    @abstractmethod
    async def generate(
        self,
        spec: CharacterSpec,
        on_progress: ProgressCallback,
    ) -> bytes:
        """Run the pipeline and return the raw GLB bytes."""
        raise NotImplementedError


class ProviderError(RuntimeError):
    """Raised by providers when generation fails."""
