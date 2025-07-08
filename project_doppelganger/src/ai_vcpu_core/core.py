import time
import asyncio
import random
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, Callable, Optional, TYPE_CHECKING

from .config import CoreConfig, CoreType, TaskPriority
from .cache import CacheHierarchy # Assuming CacheHierarchy is in cache.py

if TYPE_CHECKING: # To avoid circular import issues for type hinting
    from .ai_vcpu import TaskRequest, TaskResult # Forward reference

class CoreStatus(Enum):
    IDLE = "Idle"
    BUSY = "Busy"
    ERROR = "Error"
    INITIALIZING = "Initializing"

@dataclass
class AICore:
    config: CoreConfig
    cache_hierarchy: CacheHierarchy # Each core has access to the cache hierarchy
    status: CoreStatus = CoreStatus.IDLE
    current_task_id: Optional[str] = None

    # For simulation purposes
    _simulated_processing_time_ms: float = 0
    _tasks_processed_count: int = 0

    def __post_init__(self):
        self.status = CoreStatus.INITIALIZING
        # Simulate some initialization time
        time.sleep(random.uniform(0.001, 0.005))
        self.status = CoreStatus.IDLE

    async def process_task(self, task_request: "TaskRequest") -> "TaskResult":
        """
        Conceptual processing of a task.
        Specialized cores will override this.
        """
        if self.status == CoreStatus.BUSY:
            # This should ideally be handled by the AIVCPU scheduler
            raise Exception(f"Core {self.config.core_id} is busy.")

        self.status = CoreStatus.BUSY
        self.current_task_id = task_request.task_id
        start_time = time.monotonic()

        # Simulate work based on task complexity and core performance
        # Base processing time + cache access time + instruction specific time
        simulated_work_duration_ms = task_request.complexity * 10 # Base factor

        # Simulate cache interaction for task data
        if task_request.data_key: # Assuming task data is identified by a key
            # Reading data for the task
            _ = self.cache_hierarchy.read_hierarchical(task_request.data_key)
            # Writing results back (conceptual)
            # self.cache_hierarchy.write_hierarchical(f"result_{task_request.task_id}", {"some_result": "done"})

        # Add latency from cache operations during this task
        # This is tricky as cache latency is already in cache objects.
        # Let's assume cache_hierarchy.get_total_simulated_latency() is reset per task or accumulated globally.
        # For core-specific simulation, we add a portion of it or a fixed estimate.
        simulated_work_duration_ms += self.cache_hierarchy.get_total_simulated_latency() / 1_000_000 # Convert ns to ms
        # Reset per-task latency in cache objects for this simple model might be needed if not handled globally
        # For now, this is a rough estimate.

        # Apply performance factor if the task instruction matches core's specialty
        perf_factor = self.config.performance_factors.get(task_request.instruction, 1.0)
        simulated_work_duration_ms /= perf_factor

        # Simulate processing by sleeping
        if task_request.is_homomorphic:
            # Accessing the constant from where it's defined or define locally
            # For this example, let's assume a local/imported constant for overhead.
            # from project_doppelganger.src.security.homomorphic_processor import HomomorphicProcessor
            # overhead_multiplier = HomomorphicProcessor.HOMOMORPHIC_OVERHEAD_MULTIPLIER
            # To avoid direct import from security to core for just a constant, define it conceptually here or pass via config
            HOMOMORPHIC_OVERHEAD_MULTIPLIER_CONCEPT = 100.0 # Matching the one in HomomorphicProcessor
            simulated_work_duration_ms *= HOMOMORPHIC_OVERHEAD_MULTIPLIER_CONCEPT
            # print(f"DEBUG: Core {self.config.core_id} applying HE overhead. Original duration: {simulated_work_duration_ms / HOMOMORPHIC_OVERHEAD_MULTIPLIER_CONCEPT:.4f}ms, New: {simulated_work_duration_ms:.4f}ms")

        await asyncio.sleep(simulated_work_duration_ms / 1000.0)

        self._simulated_processing_time_ms += (time.monotonic() - start_time) * 1000
        self._tasks_processed_count += 1

        # Conceptual result
        from .ai_vcpu import TaskResult, TaskStatus # Local import to avoid circularity at module level
        result_data = {"message": f"Task {task_request.task_id} processed by {self.config.core_type.value} Core {self.config.core_id}",
                       "processed_data_preview": str(task_request.data)[:50] + "..." if task_request.data else "N/A"}

        task_result = TaskResult(
            task_id=task_request.task_id,
            request=task_request,
            status=TaskStatus.COMPLETED,
            result_data=result_data,
            core_id_executed_on=self.config.core_id
        )

        self.status = CoreStatus.IDLE
        self.current_task_id = None
        return task_result

    def get_status(self) -> Dict[str, Any]:
        return {
            "core_id": self.config.core_id,
            "core_type": self.config.core_type.value,
            "status": self.status.value,
            "current_task_id": self.current_task_id,
            "tasks_processed": self._tasks_processed_count,
            "total_simulated_processing_time_ms": self._simulated_processing_time_ms,
            "cache_stats": self.cache_hierarchy.get_all_stats() # Provides full cache stats for this core's view
        }

class GeneralPurposeCore(AICore):
    def __init__(self, config: CoreConfig, cache_hierarchy: CacheHierarchy):
        super().__init__(config, cache_hierarchy)
        if self.config.core_type != CoreType.GENERAL_PURPOSE:
            # print(f"Warning: GeneralPurposeCore initialized with type {self.config.core_type}")
            self.config.core_type = CoreType.GENERAL_PURPOSE # Correct it


class SpecializedCore(AICore):
    """Base for specialized cores, can add common specialized logic here."""
    async def process_task(self, task_request: "TaskRequest") -> "TaskResult":
        if task_request.instruction not in self.config.supported_instructions:
            # print(f"Warning: Task instruction '{task_request.instruction}' not directly supported by {self.config.core_type.value} Core {self.config.core_id}. Delegating to general processing.")
            # Fallback to base processing or raise error. For now, let base handle with default perf.
            # Or, could have a higher penalty.
            # For a stricter model, this might be an error or re-queued.
            pass
        return await super().process_task(task_request)


class LanguageModelerCore(SpecializedCore):
    def __init__(self, config: CoreConfig, cache_hierarchy: CacheHierarchy):
        super().__init__(config, cache_hierarchy)
        if self.config.core_type != CoreType.LANGUAGE_MODELER:
            self.config.core_type = CoreType.LANGUAGE_MODELER
        # Default instructions if not provided in config
        if not self.config.supported_instructions:
            self.config.supported_instructions = ["analyze_text", "generate_text_embeddings", "extract_entities", "summarize_text", "sentiment_analysis"]
        # Example performance factors
        if not self.config.performance_factors:
            self.config.performance_factors = {"analyze_text": 2.0, "sentiment_analysis": 1.8, "default": 1.5}


class VisionInterpreterCore(SpecializedCore):
    def __init__(self, config: CoreConfig, cache_hierarchy: CacheHierarchy):
        super().__init__(config, cache_hierarchy)
        if self.config.core_type != CoreType.VISION_INTERPRETER:
            self.config.core_type = CoreType.VISION_INTERPRETER
        if not self.config.supported_instructions:
            self.config.supported_instructions = ["analyze_image", "detect_objects_in_image", "generate_image_embeddings"]
        if not self.config.performance_factors:
            self.config.performance_factors = {"analyze_image": 2.5, "default": 1.2}


class FusionCore(SpecializedCore):
    def __init__(self, config: CoreConfig, cache_hierarchy: CacheHierarchy):
        super().__init__(config, cache_hierarchy)
        if self.config.core_type != CoreType.FUSION_CORE:
            self.config.core_type = CoreType.FUSION_CORE
        if not self.config.supported_instructions:
            self.config.supported_instructions = ["fuse_embeddings", "cross_modal_analysis", "integrate_sensory_data"]
        if not self.config.performance_factors:
            self.config.performance_factors = {"fuse_embeddings": 1.8, "default": 1.3}


class MemoryCore(SpecializedCore):
    def __init__(self, config: CoreConfig, cache_hierarchy: CacheHierarchy):
        super().__init__(config, cache_hierarchy)
        if self.config.core_type != CoreType.MEMORY_CORE:
            self.config.core_type = CoreType.MEMORY_CORE
        if not self.config.supported_instructions:
            self.config.supported_instructions = ["store_memory_engram", "retrieve_memory_associative", "consolidate_memory"]
        if not self.config.performance_factors:
            self.config.performance_factors = {"store_memory_engram": 2.2, "retrieve_memory_associative": 2.0, "default": 1.6}

    async def process_task(self, task_request: "TaskRequest") -> "TaskResult":
        # MemoryCore might have more complex interactions with Holographic Memory or specific CSLs
        # This is a placeholder for such specialized logic.
        # For example, a "store_memory_engram" task might always write through to HolographicMemory

        # Simulate direct interaction with holographic memory for relevant tasks
        if task_request.instruction == "store_memory_engram" and task_request.data_key and task_request.data:
            self.cache_hierarchy.holographic_memory.write(task_request.data_key, task_request.data)
            # print(f"DEBUG: MemoryCore {self.config.core_id} wrote directly to Holographic Memory for {task_request.data_key}")

        return await super().process_task(task_request)


# Example Usage:
async def main():
    from .config import AIVCPUConfig
    from .ai_vcpu import TaskRequest # For constructing a task

    # Setup a basic config and cache hierarchy for testing a core
    # This would normally come from the AIVCPU main object
    base_config = AIVCPUConfig() # Uses defaults

    # Get a LanguageModeler core config from the default AIVCPUConfig
    lm_core_config = next((c for c in base_config.specialized_core_configs if c.core_type == CoreType.LANGUAGE_MODELER), None)
    if not lm_core_config:
        print("Error: No LanguageModeler core config found in default AIVCPUConfig.")
        return

    # Each core needs its own cache hierarchy view, or a shared one passed appropriately
    # For isolated core test, create one. In AIVCPU, cores would share L2/L3.
    # Here, core_id helps L1Cache get its specific config.
    core_cache_hierarchy = CacheHierarchy(config=base_config, core_id=lm_core_config.core_id)

    lm_core = LanguageModelerCore(config=lm_core_config, cache_hierarchy=core_cache_hierarchy)
    print(f"Initialized Core: {lm_core.get_status()}")

    # Create a sample task
    sample_text_data = "This is a sample text for the Language Modeler core to analyze for sentiment."
    task_req = TaskRequest(
        task_id="task_lm_001",
        instruction="sentiment_analysis", # Supported by LanguageModelerCore
        data=sample_text_data,
        data_key="text_sample_001", # Key for cache
        priority=TaskPriority.HIGH,
        complexity=5 # Arbitrary complexity score
    )

    # Write initial data to cache so the core can read it
    lm_core.cache_hierarchy.write_hierarchical(task_req.data_key, task_req.data)

    print(f"\nSubmitting task {task_req.task_id} to {lm_core.config.core_type.value} Core {lm_core.config.core_id}...")
    result = await lm_core.process_task(task_req)
    print(f"Task completed. Status: {result.status.value}")
    print(f"Result data: {result.result_data}")
    print(f"Core status after task: {lm_core.get_status()}")

    # Test with an unsupported instruction (for this specialized core)
    task_req_unsupported = TaskRequest(
        task_id="task_lm_002",
        instruction="analyze_image", # Not for LM core
        data="some_image_data_placeholder",
        data_key="image_sample_001",
        priority=TaskPriority.MEDIUM,
        complexity=3
    )
    print(f"\nSubmitting task {task_req_unsupported.task_id} (unsupported instruction) to {lm_core.config.core_type.value} Core {lm_core.config.core_id}...")
    result_unsupported = await lm_core.process_task(task_req_unsupported)
    print(f"Task completed. Status: {result_unsupported.status.value}")
    print(f"Result data: {result_unsupported.result_data}") # Will be processed by base AICore logic
    print(f"Core status after task: {lm_core.get_status()}")


if __name__ == "__main__":
    asyncio.run(main())
