"""Vision provider implementations for visual_qa.py.

Phase 1 of SCRUM-274 introduced the provider abstraction. Phase 2 of
SCRUM-275 adds the LocalVisionProvider for sb-chat / local vLLM endpoints.
This package abstracts the vision-evaluation backend behind a single
interface so visual_qa.py can route requests to Claude, a local vLLM
server, or a future provider without changes to the orchestration layer.
"""

from .base import VisionProvider, VisionResponse
from .claude_provider import ClaudeVisionProvider
from .cloud_vl_provider import CloudVLProvider
from .fingerprint_detector import FallbackFingerprintDetector, FingerprintSettings
from .local_provider import LocalVisionProvider, PageCountMismatchError

__all__ = [
    "VisionProvider",
    "VisionResponse",
    "ClaudeVisionProvider",
    "CloudVLProvider",
    "FallbackFingerprintDetector",
    "FingerprintSettings",
    "LocalVisionProvider",
    "PageCountMismatchError",
]
