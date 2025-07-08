import unittest
import asyncio
from project_doppelganger.src.ai_vcpu_core import (
    AIVCPU, AIVCPUConfig, TaskRequest, TaskPriority, CoreType, TaskStatus
)

class TestAIVCPUIntegration(unittest.IsolatedAsyncioTestCase):

    async def test_vcpu_initialization_submit_task_and_status(self):
        # 1. Instantiate AIVCPU with a simple config
        # Using default_memory_cores=0, default_fusion_cores=0, default_vision_interpreter_cores=0 to simplify core count for test
        config = AIVCPUConfig(num_general_cores=1,
                              default_language_modeler_cores=1,
                              default_memory_cores=0,
                              default_fusion_cores=0,
                              default_vision_interpreter_cores=0)
        vcpu = AIVCPU(config=config)

        self.assertEqual(len(vcpu.cores), 2) # 1 GP + 1 LM based on this config

        # 2. Call initialize() (which maps to start())
        await vcpu.initialize()
        self.assertTrue(vcpu._is_running)
        initial_status = vcpu.get_status_overview()
        self.assertEqual(initial_status["queued_tasks"], 0)
        self.assertEqual(initial_status["active_async_tasks"], 0)

        # Verify core statuses are IDLE
        for core_stat in initial_status["cores"]:
            self.assertEqual(core_stat["status"], "Idle")

        # 3. Submit a dummy task
        dummy_task_req = TaskRequest(
            instruction="analyze_text", # Should go to LanguageModelerCore ideally
            data="This is a dummy task for integration testing.",
            data_key="dummy_task_001",
            priority=TaskPriority.MEDIUM,
            complexity=1
        )

        # Pre-populate cache for the task
        vcpu.shared_cache_hierarchy.write_hierarchical(dummy_task_req.data_key, dummy_task_req.data)

        task_id = await vcpu.submit_task(dummy_task_req)
        self.assertIsNotNone(task_id)

        status_after_submit = vcpu.get_status_overview()
        # Task might be queued or immediately active depending on timing
        # self.assertTrue(status_after_submit["queued_tasks"] == 1 or status_after_submit["active_async_tasks"] == 1)

        # 4. Wait for the task to complete and verify status
        # Allow some time for the task to be scheduled and processed
        # The simulated processing time is very short, so this should be quick.
        result = await vcpu.get_task_result(task_id, wait_timeout_sec=1.0) # Wait up to 1 sec

        self.assertIsNotNone(result, f"Task {task_id} did not complete in time.")
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.task_id, task_id)
        self.assertIsNotNone(result.core_id_executed_on)

        # Check if it ran on the LM core (core_id 1 in this config if GP is 0)
        lm_core = next((c for c in vcpu.cores if c.config.core_type == CoreType.LANGUAGE_MODELER), None)
        self.assertIsNotNone(lm_core, "Language Modeler core not found in vCPU")
        # This assertion depends on the scheduler picking the specialized core.
        # If this fails, it might indicate a scheduler logic preference issue or core availability.
        # For this basic test, we hope it picks the LM core.
        if lm_core: # Guard in case the above assertion is removed/fails
             self.assertEqual(result.core_id_executed_on, lm_core.config.core_id,
                             f"Task should have run on LM core {lm_core.config.core_id}, but ran on {result.core_id_executed_on}")


        # 5. Verify core and cache statuses (conceptual verification)
        status_after_task = vcpu.get_status_overview()
        self.assertEqual(status_after_task["total_completed"], 1)

        # The core that executed the task should have processed 1 task
        core_that_ran_task_status = next((cs for cs in status_after_task["cores"] if cs["core_id"] == result.core_id_executed_on), None)
        self.assertIsNotNone(core_that_ran_task_status)
        self.assertEqual(core_that_ran_task_status["tasks_processed"], 1)
        self.assertTrue(core_that_ran_task_status["total_simulated_processing_time_ms"] > 0)

        # Verify cache interaction (e.g., L1 cache of the executing core should show hits/misses)
        # This requires more detailed inspection of cache stats which might be complex for a simple integration test.
        # For now, just check that the data was read from Holographic Memory (as per read_hierarchical fallback)
        # or L2/L3 if it was populated there by write_hierarchical.

        # Example: Check L1 of the core that ran the task (if it has L1)
        core_obj = next((c for c in vcpu.cores if c.config.core_id == result.core_id_executed_on), None)
        if core_obj and core_obj.cache_hierarchy.l1:
            l1_stats = core_obj.cache_hierarchy.l1.get_stats()
            # After one read for the task data_key
            self.assertTrue(l1_stats["hits"] > 0 or l1_stats["misses"] > 0, "L1 cache of executing core shows no activity.")

        # Check shared L2 cache activity
        l2_stats = vcpu.shared_cache_hierarchy.l2.get_stats()
        self.assertTrue(l2_stats["hits"] > 0 or l2_stats["misses"] > 0, "Shared L2 cache shows no activity.")

        # Check Holographic Memory had a read (misses indicate it was read from, hits if already there)
        hm_stats = vcpu.shared_cache_hierarchy.holographic_memory.get_stats()
        # The write_hierarchical writes to HM, then read_hierarchical will find it there.
        # So, we expect at least one hit on HM for the data_key.
        self.assertTrue(hm_stats["hits"] > 0, "Holographic Memory should have a hit for the task data.")


        # 6. Stop the vCPU
        await vcpu.stop()
        self.assertFalse(vcpu._is_running)
        # Ensure scheduler task is cleaned up
        self.assertIsNone(vcpu._scheduler_task)


if __name__ == '__main__':
    asyncio.run(unittest.main())
