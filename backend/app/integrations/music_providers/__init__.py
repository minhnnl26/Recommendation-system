"""Provider adapters for metadata and playback feasibility experiments."""

from .models import NormalizedTrack
from .service import MusicProviderService

__all__ = ["MusicProviderService", "NormalizedTrack"]
