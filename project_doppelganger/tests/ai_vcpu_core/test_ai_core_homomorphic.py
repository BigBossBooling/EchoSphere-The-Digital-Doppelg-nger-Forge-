import unittest
import asyncio
import time # For checking processing time differences

from project_doppelganger.src.ai_vcpu_core import (
    AIVCPUConfig,
    CoreConfig,
    CoreType,
    TaskPriority,
    CacheHierarchy, # Needed by AICore
    AICore # The class to test
)
from project_doppelganger.src.ai_vcpu_core.ai_vcpu import TaskRequest # TaskRequest definition
# HOMOMORPHIC_OVERHEAD_MULTIPLIER_CONCEPT is defined inside AICore.process_task for simulation
# We will check its effect.

class TestAICoreHomomorphicOverhead(unittest.IsolatedAsyncioTestCase):

    async def test_homomorphic_task_incurs_overhead(self):
        # Setup a simple core
        core_conf = CoreConfig(core_id=0, core_type=CoreType.GENERAL_PURPOSE)
        # AIVCPUConfig is needed for CacheHierarchy, even if not fully utilized here
        vcpu_config = AIVCPUConfig()
        cache_hierarchy = CacheHierarchy(config=vcpu_config, core_id=0)
        core = AICore(config=core_conf, cache_hierarchy=cache_hierarchy)

        # Standard Task
        standard_task_req = TaskRequest(
            task_id="std_task_1",
            instruction="test_instruction",
            complexity=1, # Keep complexity low and equal for comparison
            is_homomorphic=False
        )

        start_time_std = time.perf_counter()
        await core.process_task(standard_task_req)
        end_time_std = time.perf_counter()
        duration_std_ms = (end_time_std - start_time_std) * 1000

        # Reset core status for next task (or use a new core instance)
        core.status = "Idle"
        core.current_task_id = None
        # Note: _simulated_processing_time_ms in core accumulates, which is fine.
        # We are comparing wall-clock execution of process_task calls.

        # Homomorphic Task
        homomorphic_task_req = TaskRequest(
            task_id="he_task_1",
            instruction="test_instruction_he", # Can be same or different
            complexity=1, # Same complexity
            is_homomorphic=True # The key difference
        )

        start_time_he = time.perf_counter()
        await core.process_task(homomorphic_task_req)
        end_time_he = time.perf_counter()
        duration_he_ms = (end_time_he - start_time_he) * 1000

        print(f"Standard task duration: {duration_std_ms:.4f} ms (simulated sleep part)")
        print(f"Homomorphic task duration: {duration_he_ms:.4f} ms (simulated sleep part)")

        # The HE task's simulated sleep should be ~100x longer than standard task's.
        # We need to account for the fixed overhead of the process_task method itself (asyncio context switches, etc.)
        # So, duration_he_ms will not be exactly 100x duration_std_ms, but the sleep portion will be.
        # The `simulated_work_duration_ms` inside `process_task` is what gets multiplied.
        # A rough check:
        self.assertTrue(duration_he_ms > duration_std_ms * 10,
                        "Homomorphic task duration should be significantly longer than standard task.")

        # A more precise check would involve inspecting the `simulated_work_duration_ms`
        # if it were exposed, or by ensuring the sleep time is proportionally longer.
        # The current test checks the effect on wall-clock time of the call.

        # Check core's accumulated processing time (conceptual, not wall-clock)
        # This is tricky because _simulated_processing_time_ms is what the core *thinks* it spent.
        # The actual sleep time is derived from task_request.complexity and then multiplied.
        # Let's look at the core's internal accounting of *simulated* time, which should reflect the multiplier.

        # Get the _simulated_processing_time_ms recorded by the core for each task.
        # This requires a bit of access to the core's internals or modifying it to return this.
        # For now, the wall-clock check above is the primary assertion.
        # If core.get_status() exposed the last task's simulated duration, we could use that.
        # The `_simulated_processing_time_ms` is cumulative.
        # The first task processing time: core_status_after_std["total_simulated_processing_time_ms"]
        # The second task processing time: core_status_after_he["total_simulated_processing_time_ms"] - core_status_after_std["total_simulated_processing_time_ms"]

        # This test primarily ensures the `is_homomorphic = True` path is taken and results in longer processing.


if __name__ == '__main__':
    unittest.main()
