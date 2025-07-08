# This file makes Python treat the 'ai_vcpu_core' directory as a package.

from .config import AIVCPUConfig, CoreConfig, CacheConfig, CoreType, TaskPriority
from .cache import CacheEntry, CacheHierarchy, L1Cache, L2Cache, L3Cache, HolographicMemoryCache, ContextSpecificCacheLayer
from .core import AICore, SpecializedCore, GeneralPurposeCore, FusionCore, LanguageModelerCore, VisionInterpreterCore, MemoryCore, CoreStatus
from .ai_vcpu import AIVCPU, TaskRequest, TaskResult, TaskStatus

# Define a default AI-vCPU configuration for easy import if needed elsewhere
DEFAULT_CONFIG = AIVCPUConfig()

# Expose some key enums directly for convenience
# from .config import CoreType, TaskPriority # Already done by first line
# from .core import CoreStatus # Already done by third line
# from .ai_vcpu import TaskStatus # Already done by fourth line
