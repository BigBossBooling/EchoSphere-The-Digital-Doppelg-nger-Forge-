import asyncio
import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Coroutine

from .config import AIVCPUConfig, CoreConfig, CoreType, TaskPriority
from .cache import CacheHierarchy
from .core import AICore, GeneralPurposeCore, LanguageModelerCore, VisionInterpreterCore, FusionCore, MemoryCore, CoreStatus

class TaskStatus(Enum):
    PENDING = "Pending"
    SCHEDULED = "Scheduled"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"

@dataclass
class TaskRequest:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    instruction: str # e.g., "analyze_text", "extract_entities", "fuse_data"
    data: Any = None # The actual data payload for the task
    data_key: Optional[str] = None # Key to retrieve/store data in cache if not directly in payload
    priority: TaskPriority = TaskPriority.MEDIUM
    complexity: int = 1 # Arbitrary measure (1-10) affecting processing time
    required_core_type: Optional[CoreType] = None # Request a specific type of core
    dependencies: List[str] = field(default_factory=list) # List of task_ids this task depends on
    callback_url: Optional[str] = None # For async notification (conceptual)
    is_homomorphic: bool = False # If True, data is EncryptedData and operations incur overhead
    metadata: Dict[str, Any] = field(default_factory=dict) # Other task parameters

@dataclass
class TaskResult:
    task_id: str
    request: TaskRequest
    status: TaskStatus
    result_data: Optional[Any] = None
    error_message: Optional[str] = None
    core_id_executed_on: Optional[int] = None
    execution_time_ms: float = 0 # Actual execution time on core

class AIVCPU:
    """
    Conceptual simulation of an AI-vCPU.
    Manages cores, a shared cache hierarchy, and a task queue.
    """
    def __init__(self, config: Optional[AIVCPUConfig] = None):
        self.config = config if config else AIVCPUConfig()

        # Initialize shared cache hierarchy components (L2, L3, HM, CSLs)
        # Cores will get a reference to this or a view of it.
        self.shared_cache_hierarchy = CacheHierarchy(config=self.config, core_id=None) # core_id=None for shared caches

        self.cores: List[AICore] = []
        self._initialize_cores()

        self.task_queue: asyncio.PriorityQueue[Tuple[int, TaskRequest]] = asyncio.PriorityQueue()
        self.active_tasks: Dict[str, asyncio.Task] = {} # For managing running asyncio tasks
        self.task_results: Dict[str, TaskResult] = {} # Store results of completed/failed tasks

        self._is_running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._total_tasks_submitted = 0
        self._total_tasks_completed = 0
        self._total_tasks_failed = 0

    def _initialize_cores(self):
        core_id_counter = 0
        # General Purpose Cores
        for _ in range(self.config.num_general_cores):
            gp_config = CoreConfig(core_id=core_id_counter, core_type=CoreType.GENERAL_PURPOSE)
            # General cores also need their L1 cache, create a CacheHierarchy view for them
            core_cache_view = CacheHierarchy(config=self.config, core_id=core_id_counter)
            # Link its shared components to the AIVCPU's shared ones (conceptual linking)
            core_cache_view.l2 = self.shared_cache_hierarchy.l2
            core_cache_view.l3 = self.shared_cache_hierarchy.l3
            core_cache_view.holographic_memory = self.shared_cache_hierarchy.holographic_memory
            core_cache_view.context_caches = self.shared_cache_hierarchy.context_caches

            self.cores.append(GeneralPurposeCore(config=gp_config, cache_hierarchy=core_cache_view))
            core_id_counter += 1

        # Specialized Cores from config
        for spec_core_conf in self.config.specialized_core_configs:
            # Ensure core_id is unique if it was manually set in config, or assign next
            # For simplicity, we assume config provides unique core_ids or they are sequential from above
            # If spec_core_conf.core_id conflicts, it should be handled (e.g., re-assign or error)
            # Here, we trust config's core_id if it's part of specialized_core_configs

            core_cache_view = CacheHierarchy(config=self.config, core_id=spec_core_conf.core_id)
            core_cache_view.l2 = self.shared_cache_hierarchy.l2
            core_cache_view.l3 = self.shared_cache_hierarchy.l3
            core_cache_view.holographic_memory = self.shared_cache_hierarchy.holographic_memory
            core_cache_view.context_caches = self.shared_cache_hierarchy.context_caches

            if spec_core_conf.core_type == CoreType.LANGUAGE_MODELER:
                self.cores.append(LanguageModelerCore(config=spec_core_conf, cache_hierarchy=core_cache_view))
            elif spec_core_conf.core_type == CoreType.VISION_INTERPRETER:
                self.cores.append(VisionInterpreterCore(config=spec_core_conf, cache_hierarchy=core_cache_view))
            elif spec_core_conf.core_type == CoreType.FUSION_CORE:
                self.cores.append(FusionCore(config=spec_core_conf, cache_hierarchy=core_cache_view))
            elif spec_core_conf.core_type == CoreType.MEMORY_CORE:
                self.cores.append(MemoryCore(config=spec_core_conf, cache_hierarchy=core_cache_view))
            # Add other specialized types here
            else:
                print(f"Warning: Unknown specialized core type in config: {spec_core_conf.core_type}. Skipping.")
            # core_id_counter should track based on actual cores added

        print(f"AIVCPU initialized with {len(self.cores)} cores.")

    async def submit_task(self, task_request: TaskRequest) -> str:
        """Submits a task to the AIVCPU's processing queue."""
        if not self._is_running:
            # print("Warning: AIVCPU is not running. Starting scheduler.")
            await self.start() # Auto-start if not running

        self._total_tasks_submitted +=1
        # Priority queue stores (priority_value, task_request). Lower value = higher priority.
        # We negate TaskPriority.value because asyncio.PriorityQueue is a min-heap.
        await self.task_queue.put((-task_request.priority.value, task_request))
        self.task_results[task_request.task_id] = TaskResult(task_request.task_id, task_request, TaskStatus.PENDING)
        # print(f"Task {task_request.task_id} submitted with priority {task_request.priority.name}.")
        return task_request.task_id

    async def _scheduler_loop(self):
        """Continuously tries to schedule tasks from the queue to available cores."""
        self._is_running = True
        print("AIVCPU Scheduler started.")
        while self._is_running or not self.task_queue.empty():
            try:
                # Wait for a task with a timeout to allow checking _is_running
                _, task_req = await asyncio.wait_for(self.task_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                if not self._is_running and self.task_queue.empty() and not self.active_tasks:
                    break # Exit if stopped, queue empty, and no active tasks
                continue # Check _is_running again or wait for new tasks

            # Basic dependency check (conceptual, assumes dependencies are already completed)
            if task_req.dependencies:
                all_deps_met = True
                for dep_id in task_req.dependencies:
                    dep_result = self.task_results.get(dep_id)
                    if not dep_result or dep_result.status != TaskStatus.COMPLETED:
                        all_deps_met = False
                        break
                if not all_deps_met:
                    # print(f"Task {task_req.task_id} deferred due to unmet dependencies. Re-queuing.")
                    await self.task_queue.put((-task_req.priority.value, task_req)) # Re-queue with original priority
                    self.task_queue.task_done() # Mark this attempt as done
                    await asyncio.sleep(0.05) # Small delay before retrying queue
                    continue

            selected_core = self._find_available_core(task_req)

            if selected_core:
                # print(f"Scheduling task {task_req.task_id} on Core {selected_core.config.core_id} ({selected_core.config.core_type.value})")
                self.task_results[task_req.task_id].status = TaskStatus.SCHEDULED
                # Create an asyncio.Task to run the core's process_task method
                async_task = asyncio.create_task(self._execute_on_core(selected_core, task_req))
                self.active_tasks[task_req.task_id] = async_task
            else:
                # print(f"No suitable core currently available for task {task_req.task_id}. Re-queuing.")
                await self.task_queue.put((-task_req.priority.value, task_req)) # Re-queue
                await asyncio.sleep(0.01) # Prevent tight loop if no cores are ever available

            self.task_queue.task_done()

        self._is_running = False # Ensure it's marked false if loop exits
        print("AIVCPU Scheduler stopped.")


    def _find_available_core(self, task_request: TaskRequest) -> Optional[AICore]:
        """Finds an appropriate and available core for the task."""
        # Priority:
        # 1. Requested core type, if specified and available.
        # 2. Specialized core that supports the instruction, if available.
        # 3. Any available General Purpose core.
        # 4. Any available Specialized core (even if not perfectly matched, less efficient).

        available_cores = [core for core in self.cores if core.status == CoreStatus.IDLE]
        if not available_cores: return None

        # 1. Requested core type
        if task_request.required_core_type:
            for core in available_cores:
                if core.config.core_type == task_request.required_core_type:
                    return core

        # 2. Specialized core supporting the instruction
        for core in available_cores:
            if core.config.core_type != CoreType.GENERAL_PURPOSE and \
               task_request.instruction in core.config.supported_instructions:
                return core

        # 3. General Purpose core
        for core in available_cores:
            if core.config.core_type == CoreType.GENERAL_PURPOSE:
                return core

        # 4. Any other available specialized core (least preferred if not matched)
        # This could be refined based on some compatibility score.
        # For now, just pick the first available if list is not empty.
        if available_cores: # Should always be true if we got here from initial check
            return random.choice(available_cores) # Fallback to any idle core

        return None


    async def _execute_on_core(self, core: AICore, task_request: TaskRequest):
        """Wrapper to execute a task on a core and handle results."""
        start_time = time.monotonic()
        self.task_results[task_request.task_id].status = TaskStatus.RUNNING
        try:
            result = await core.process_task(task_request)
            result.execution_time_ms = (time.monotonic() - start_time) * 1000
            self.task_results[task_request.task_id] = result
            if result.status == TaskStatus.COMPLETED:
                self._total_tasks_completed +=1
            else: # Should ideally not happen if core.process_task sets it to FAILED
                self._total_tasks_failed +=1
                if not result.error_message: result.error_message = "Core processing error, status not COMPLETED."
        except Exception as e:
            exec_time = (time.monotonic() - start_time) * 1000
            self.task_results[task_request.task_id] = TaskResult(
                task_id=task_request.task_id,
                request=task_request,
                status=TaskStatus.FAILED,
                error_message=str(e),
                core_id_executed_on=core.config.core_id,
                execution_time_ms=exec_time
            )
            self._total_tasks_failed +=1
            print(f"Error executing task {task_request.task_id} on core {core.config.core_id}: {e}")
        finally:
            if task_request.task_id in self.active_tasks:
                del self.active_tasks[task_request.task_id]
            # print(f"Task {task_request.task_id} finished processing on core {core.config.core_id}. Status: {self.task_results[task_request.task_id].status.value}")


    async def start(self):
        if self._is_running:
            # print("AIVCPU is already running.")
            return
        if self._scheduler_task and not self._scheduler_task.done():
            # print("Scheduler task exists but AIVCPU not marked running. This is unusual.")
            return

        self.shared_cache_hierarchy.flush_all() # Clear caches on start
        for core in self.cores: # Reset core statuses and individual L1s
            core.status = CoreStatus.IDLE
            core.current_task_id = None
            if core.cache_hierarchy.l1:
                core.cache_hierarchy.l1.flush()

        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        # print("AIVCPU start initiated.")
        await asyncio.sleep(0.01) # Give scheduler a moment to start up

    async def stop(self, graceful=True):
        print("AIVCPU stop initiated.")
        self._is_running = False # Signal scheduler to stop picking new tasks

        if graceful:
            # Wait for the queue to be empty and active tasks to finish
            # print("Graceful shutdown: waiting for queue and active tasks...")
            await self.task_queue.join() # Wait for all items put in queue to be gotten and task_done() called
            if self.active_tasks:
                await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)
            # print("All active tasks completed.")
        else:
            # print("Immediate shutdown: cancelling active tasks...")
            for task_id, async_task_obj in list(self.active_tasks.items()): # list() for safe iteration
                async_task_obj.cancel()
                self.task_results[task_id].status = TaskStatus.CANCELLED
                self.task_results[task_id].error_message = "Cancelled due to AIVCPU immediate stop."
                del self.active_tasks[task_id]
            # Clear the queue
            while not self.task_queue.empty():
                try:
                    _, task_req = self.task_queue.get_nowait()
                    self.task_results[task_req.task_id].status = TaskStatus.CANCELLED
                    self.task_results[task_req.task_id].error_message = "Cancelled due to AIVCPU immediate stop (was in queue)."
                    self.task_queue.task_done()
                except asyncio.QueueEmpty:
                    break

        if self._scheduler_task and not self._scheduler_task.done():
            try:
                # print("Waiting for scheduler task to finish...")
                await asyncio.wait_for(self._scheduler_task, timeout=1.0)
            except asyncio.TimeoutError:
                print("Scheduler task did not finish in time, cancelling.")
                self_scheduler_task.cancel()
            except asyncio.CancelledError:
                print("Scheduler task was cancelled.")

        self._scheduler_task = None # Clear the task object
        print("AIVCPU stopped.")

    async def get_task_result(self, task_id: str, wait_timeout_sec: Optional[float] = None) -> Optional[TaskResult]:
        """
        Retrieves the result of a task. If `wait_timeout_sec` is provided,
        it will wait for the task to complete or fail.
        """
        if wait_timeout_sec is None:
            return self.task_results.get(task_id)

        start_wait = time.monotonic()
        while time.monotonic() - start_wait < wait_timeout_sec:
            result = self.task_results.get(task_id)
            if result and result.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                return result
            await asyncio.sleep(0.02) # Poll interval

        # Timeout reached
        return self.task_results.get(task_id) # Return current state after timeout


    def get_status_overview(self) -> Dict[str, Any]:
        return {
            "is_running": self._is_running,
            "queued_tasks": self.task_queue.qsize(),
            "active_async_tasks": len(self.active_tasks),
            "total_submitted": self._total_tasks_submitted,
            "total_completed": self._total_tasks_completed,
            "total_failed": self._total_tasks_failed,
            "cores": [core.get_status() for core in self.cores],
            "shared_cache_summary": { # Summary, not full stats to keep it brief
                "L2_entries": self.shared_cache_hierarchy.l2.get_stats()["current_entries"],
                "L3_entries": self.shared_cache_hierarchy.l3.get_stats()["current_entries"] if self.shared_cache_hierarchy.l3 else "N/A",
                "HM_entries": self.shared_cache_hierarchy.holographic_memory.get_stats()["current_entries"]
            }
        }

    # Alias for initialization as per plan
    async def initialize(self): # `initialize` was in the plan, maps to `start`
        await self.start()


# Example Usage
async def example_run():
    print("--- AIVCPU Example Run ---")
    vcpu_config = AIVCPUConfig(num_general_cores=1, default_language_modeler_cores=1, default_fusion_cores=0, default_memory_cores=0)
    vcpu = AIVCPU(config=vcpu_config)

    await vcpu.start() # Start the scheduler

    # Submit some tasks
    task_req1 = TaskRequest(instruction="analyze_text", data="Some text for analysis.", priority=TaskPriority.HIGH, complexity=3, data_key="text1")
    task_req2 = TaskRequest(instruction="extract_entities", data="More text with entities like Paris and London.", priority=TaskPriority.MEDIUM, complexity=5, data_key="text2", required_core_type=CoreType.LANGUAGE_MODELER)
    task_req3 = TaskRequest(instruction="generic_compute", data={"value": 42}, priority=TaskPriority.LOW, complexity=2, data_key="compute1")
    task_req_dep = TaskRequest(instruction="summarize_text", data="Summary based on text1", priority=TaskPriority.HIGH, complexity=4, data_key="text1_summary", dependencies=[task_req1.task_id])


    print(f"Submitting task {task_req1.task_id} (High Prio Text Analysis)")
    await vcpu.submit_task(task_req1)

    print(f"Submitting task {task_req2.task_id} (Med Prio Entity Extraction for LM Core)")
    await vcpu.submit_task(task_req2)

    print(f"Submitting task {task_req3.task_id} (Low Prio Generic Compute)")
    await vcpu.submit_task(task_req3)

    print(f"Submitting task {task_req_dep.task_id} (High Prio Summarize, depends on {task_req1.task_id})")
    await vcpu.submit_task(task_req_dep)


    print("\n--- AIVCPU Status after submissions ---")
    print(vcpu.get_status_overview())

    # Wait for tasks to complete (or a timeout)
    print("\nWaiting for tasks to complete...")
    await asyncio.sleep(1.0) # Allow time for tasks to be processed (adjust based on simulated work)
    # In a real app, you'd await get_task_result with timeout or use callbacks

    print("\n--- Task Results ---")
    for task_id_to_check in [task_req1.task_id, task_req2.task_id, task_req3.task_id, task_req_dep.task_id]:
        result = await vcpu.get_task_result(task_id_to_check, wait_timeout_sec=0.5) # Wait a bit more
        if result:
            print(f"Result for {task_id_to_check}: Status={result.status.value}, Core={result.core_id_executed_on}, Error='{result.error_message}', Data='{str(result.result_data)[:80]}...'")
        else:
            print(f"Result for {task_id_to_check} not found or timed out.")

    print("\n--- Final AIVCPU Status ---")
    overview = vcpu.get_status_overview()
    for core_stat in overview['cores']:
        print(f"  Core {core_stat['core_id']} ({core_stat['core_type']}): Status={core_stat['status']}, Tasks Processed={core_stat['tasks_processed']}")

    await vcpu.stop()
    print("--- AIVCPU Example Run Finished ---")

if __name__ == "__main__":
    asyncio.run(example_run())
