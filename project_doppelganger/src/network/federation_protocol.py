import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable

from project_doppelganger.src.ai_vcpu_core import AIVCPU, TaskRequest, TaskResult, TaskStatus

# --- Message Types for Federation ---

@dataclass
class FederatedTaskRequest:
    """A task request being sent from one AIVCPU node to another."""
    original_task_request: TaskRequest # The task to be executed remotely
    source_node_id: str # ID of the AIVCPU node sending the request
    target_node_id: Optional[str] = None # Specific target, or None for broadcast/discovery
    federated_request_id: str = field(default_factory=lambda: f"fed_req_{uuid.uuid4()}")
    # Metadata for federation, e.g., hop count, security tokens (conceptual)
    federation_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class FederatedTaskResponse:
    """A response to a FederatedTaskRequest."""
    federated_request_id: str
    original_task_id: str
    task_result: TaskResult # The result from the remote AIVCPU
    source_node_id: str # ID of the AIVCPU node that executed the task and is sending response
    destination_node_id: str # ID of the AIVCPU node that originally requested

# --- Conceptual Federation Node and Manager ---

class FederationNode:
    """
    Represents a single AIVCPU instance participating in the federation.
    This class would wrap an AIVCPU and handle network communication (simulated).
    """
    def __init__(self, node_id: str, local_vcpu: AIVCPU, federation_manager: "FederationManager"):
        self.node_id = node_id
        self.local_vcpu = local_vcpu
        self.federation_manager = federation_manager # To send messages to other nodes
        self.is_online: bool = True # Conceptual status
        print(f"FederationNode '{self.node_id}' initialized with AIVCPU (Cores: {len(local_vcpu.cores)}).")

    async def receive_federated_task_request(self, fed_request: FederatedTaskRequest) -> Optional[FederatedTaskResponse]:
        """Receives a task request from another node and processes it locally."""
        if not self.is_online:
            print(f"Node '{self.node_id}' is offline. Cannot process federated request {fed_request.federated_request_id}.")
            # In a real system, might return an error response.
            return None

        print(f"Node '{self.node_id}' received federated task '{fed_request.original_task_request.task_id}' (FedID: {fed_request.federated_request_id}) from '{fed_request.source_node_id}'.")

        # Submit the original task to the local AIVCPU
        # Ensure the task_id is unique if there's any chance of collision, or use the original.
        # For this simulation, we assume the original TaskRequest is directly executable.
        await self.local_vcpu.submit_task(fed_request.original_task_request)

        # Wait for the local AIVCPU to complete the task
        # The timeout here is crucial in a real system.
        task_result = await self.local_vcpu.get_task_result(fed_request.original_task_request.task_id, wait_timeout_sec=10.0) # Conceptual timeout

        if not task_result: # Task timed out or other issue
            print(f"  Node '{self.node_id}': Task '{fed_request.original_task_request.task_id}' did not complete locally in time for federated response.")
            # Create a FAILED TaskResult to send back
            from project_doppelganger.src.ai_vcpu_core.ai_vcpu import TaskStatus # Local import
            task_result = TaskResult(
                task_id=fed_request.original_task_request.task_id,
                request=fed_request.original_task_request,
                status=TaskStatus.FAILED,
                error_message=f"Processing timed out on federated node {self.node_id}"
            )

        print(f"  Node '{self.node_id}': Task '{task_result.task_id}' processed locally. Status: {task_result.status.value}. Sending response to '{fed_request.source_node_id}'.")
        return FederatedTaskResponse(
            federated_request_id=fed_request.federated_request_id,
            original_task_id=task_result.task_id,
            task_result=task_result,
            source_node_id=self.node_id, # This node is the source of the response
            destination_node_id=fed_request.source_node_id
        )

    async def send_federated_task_request(self, task_to_offload: TaskRequest, target_node_id: str) -> Optional[FederatedTaskResponse]:
        """Sends a task to a specific target node for execution."""
        if not self.is_online: return None

        fed_req = FederatedTaskRequest(
            original_task_request=task_to_offload,
            source_node_id=self.node_id,
            target_node_id=target_node_id
        )
        print(f"Node '{self.node_id}' sending task '{task_to_offload.task_id}' to node '{target_node_id}' (FedID: {fed_req.federated_request_id})...")
        # Simulate sending to manager, which routes it
        return await self.federation_manager.route_request_to_node(target_node_id, fed_req)


class FederationManager:
    """
    Manages a conceptual network of FederationNodes (AIVCPUs).
    Simulates routing of federated task requests and responses.
    In a real system, this would be a distributed protocol, not a central manager.
    """
    def __init__(self):
        self.nodes: Dict[str, FederationNode] = {}
        self._pending_federated_responses: Dict[str, asyncio.Future] = {} # fed_req_id -> Future for result
        print("Conceptual FederationManager initialized.")

    def register_node(self, node: FederationNode):
        if node.node_id in self.nodes:
            print(f"Warning: FederationNode '{node.node_id}' already registered.")
            return
        self.nodes[node.node_id] = node
        print(f"FederationNode '{node.node_id}' registered with manager.")

    def unregister_node(self, node_id: str):
        if node_id in self.nodes:
            del self.nodes[node_id]
            print(f"FederationNode '{node_id}' unregistered.")

    async def route_request_to_node(self, target_node_id: str, fed_request: FederatedTaskRequest) -> Optional[FederatedTaskResponse]:
        """Simulates routing a request to a target node and getting a response."""
        target_node = self.nodes.get(target_node_id)
        if not target_node or not target_node.is_online:
            print(f"  FederationManager: Target node '{target_node_id}' not found or offline for FedID {fed_request.federated_request_id}.")
            return None # Or a response indicating target unavailable

        # Create a future to await the response for this federated request
        response_future: asyncio.Future[FederatedTaskResponse] = asyncio.Future()
        self._pending_federated_responses[fed_request.federated_request_id] = response_future

        # "Send" the request to the target node (direct call in simulation)
        # This needs to be non-blocking for the sender if target takes time.
        # So, target_node.receive_federated_task_request should be scheduled.
        async def process_on_target_and_fulfill_future():
            response = await target_node.receive_federated_task_request(fed_request) # type: ignore
            if response:
                # In a real system, response would come back over network. Here we fulfill the future.
                # print(f"DEBUG: Fulfilling future for {fed_request.federated_request_id} with response from {response.source_node_id}")
                if fed_request.federated_request_id in self._pending_federated_responses:
                    self._pending_federated_responses[fed_request.federated_request_id].set_result(response)
                    # del self._pending_federated_responses[fed_request.federated_request_id] # Clean up after set
                else:
                    print(f"DEBUG: Future for {fed_request.federated_request_id} already removed or not found when trying to set result.")

            else: # No response or error from target node processing
                # print(f"DEBUG: Fulfilling future for {fed_request.federated_request_id} with an exception (no response from target).")
                if fed_request.federated_request_id in self._pending_federated_responses:
                    self._pending_federated_responses[fed_request.federated_request_id].set_exception(
                        RuntimeError(f"No response or error from target node {target_node_id} for FedID {fed_request.federated_request_id}")
                    )
                    # del self._pending_federated_responses[fed_request.federated_request_id]
                else:
                     print(f"DEBUG: Future for {fed_request.federated_request_id} already removed when trying to set exception.")


        asyncio.create_task(process_on_target_and_fulfill_future())

        try:
            # Wait for the future to be resolved with a timeout
            return await asyncio.wait_for(response_future, timeout=15.0) # Conceptual timeout for federated op
        except asyncio.TimeoutError:
            print(f"  FederationManager: Timeout waiting for response from '{target_node_id}' for FedID {fed_request.federated_request_id}.")
            # Clean up future if it timed out
            if fed_request.federated_request_id in self._pending_federated_responses:
                 del self._pending_federated_responses[fed_request.federated_request_id]
            return None
        except Exception as e: # Other errors like the RuntimeError set above
            print(f"  FederationManager: Error waiting for response from '{target_node_id}' for FedID {fed_request.federated_request_id}: {e}")
            if fed_request.federated_request_id in self._pending_federated_responses:
                 del self._pending_federated_responses[fed_request.federated_request_id]
            return None
        finally:
            # Ensure cleanup if future was resolved normally but still in dict (shouldn't happen with current logic)
            if fed_request.federated_request_id in self._pending_federated_responses:
                 del self._pending_federated_responses[fed_request.federated_request_id]


    # Conceptual: Task discovery or load balancing logic
    async def find_suitable_node_for_task(self, task_request: TaskRequest) -> Optional[str]:
        """Conceptually finds a suitable node based on load, capabilities, data locality."""
        # Simple strategy: pick a random available node that isn't self (if called from a node)
        # or a node that matches required_core_type.
        # This would be a complex part of a real federation protocol.
        available_nodes = [nid for nid, node in self.nodes.items() if node.is_online]
        if not available_nodes: return None

        # If task has a required core type, try to find a node with such a core available
        if task_request.required_core_type:
            for node_id in available_nodes:
                node = self.nodes[node_id]
                if any(core.config.core_type == task_request.required_core_type and core.status == "Idle" for core in node.local_vcpu.cores): # CoreStatus enum
                    return node_id # Found a node with an idle core of the required type

        # Fallback: random choice among available nodes
        return random.choice(available_nodes) if available_nodes else None


# Example Usage:
async def main_federation_demo():
    print("--- Federation Protocol Demo (Conceptual) ---")

    # 1. Create AIVCPU instances (these will be wrapped by FederationNodes)
    # Node A: General purpose heavy
    config_a = AIVCPUConfig(num_general_cores=4, default_language_modeler_cores=1)
    vcpu_a = AIVCPU(config=config_a)
    await vcpu_a.start()

    # Node B: Language modeler heavy
    config_b = AIVCPUConfig(num_general_cores=1, default_language_modeler_cores=4)
    vcpu_b = AIVCPU(config=config_b)
    await vcpu_b.start()

    # 2. Create FederationManager and FederationNodes
    manager = FederationManager()
    node_a = FederationNode(node_id="NodeA_GenHeavy", local_vcpu=vcpu_a, federation_manager=manager)
    node_b = FederationNode(node_id="NodeB_LMHeavy", local_vcpu=vcpu_b, federation_manager=manager)

    manager.register_node(node_a)
    manager.register_node(node_b)

    # 3. Node A wants to offload a language-intensive task to Node B
    print("\nScenario: Node A offloading LM task to Node B...")
    lm_task = TaskRequest(
        instruction="analyze_text_for_traits", # Language Modeler task
        data={"text": "This is a complex text requiring deep NLP analysis."},
        priority="HIGH", # TaskPriority Enum
        complexity=8,
        required_core_type="LANGUAGE_MODELER" # CoreType Enum
    )
    # Ensure enums are used if TaskRequest expects them
    from project_doppelganger.src.ai_vcpu_core import TaskPriority, CoreType
    lm_task.priority = TaskPriority.HIGH
    lm_task.required_core_type = CoreType.LANGUAGE_MODELER


    federated_response = await node_a.send_federated_task_request(lm_task, target_node_id="NodeB_LMHeavy")

    if federated_response and federated_response.task_result:
        print(f"Node A received response for FedID '{federated_response.federated_request_id}' (Original Task ID: {federated_response.original_task_id})")
        print(f"  Task Status on Node B: {federated_response.task_result.status.value}")
        print(f"  Executed by Core ID on Node B: {federated_response.task_result.core_id_executed_on}")
        print(f"  Result Preview: {str(federated_response.task_result.result_data)[:100]}...")
        assert federated_response.task_result.status == TaskStatus.COMPLETED
        # Check if it ran on an LM core on Node B (IDs might vary, check type)
        core_on_b = next((c for c in vcpu_b.cores if c.config.core_id == federated_response.task_result.core_id_executed_on), None)
        assert core_on_b is not None and core_on_b.config.core_type == CoreType.LANGUAGE_MODELER
    else:
        print("Node A: Did not receive a successful federated response or task failed on Node B.")

    # 4. Conceptual: Node B needs a general task done, might try to find any node (could be itself or Node A)
    print("\nScenario: Node B looking for any node for a general task...")
    general_task = TaskRequest(instruction="generic_computation", data={"value": 100}, complexity=3, priority=TaskPriority.LOW)

    # Simulate node discovery (in a real system, this is complex)
    # For demo, let's say manager helps find a node.
    # This is a bit artificial as node_b would typically just run it if it can.
    # The use case is more for when a node is overloaded or lacks capability.

    # Let's assume Node B is overloaded and wants to offload.
    suitable_node_id_for_general_task = await manager.find_suitable_node_for_task(general_task)
    if suitable_node_id_for_general_task:
        print(f"Node B found suitable node '{suitable_node_id_for_general_task}' for general task.")
        if suitable_node_id_for_general_task == node_b.node_id:
            print("  (It found itself, which is fine if not overloaded. For demo, let's assume it would prefer to offload if possible).")
            # To force offload for demo, let's pick Node A if available and not self
            if suitable_node_id_for_general_task == node_b.node_id and "NodeA_GenHeavy" in manager.nodes:
                suitable_node_id_for_general_task = "NodeA_GenHeavy"
                print(f"  Forcing offload to {suitable_node_id_for_general_task} for demo.")


        if suitable_node_id_for_general_task != node_b.node_id : # If it's not itself
            general_task_response = await node_b.send_federated_task_request(general_task, target_node_id=suitable_node_id_for_general_task)
            if general_task_response and general_task_response.task_result:
                 print(f"Node B received response for general task from '{general_task_response.source_node_id}': Status {general_task_response.task_result.status.value}")
                 assert general_task_response.task_result.status == TaskStatus.COMPLETED
            else:
                print(f"Node B: General task offload to '{suitable_node_id_for_general_task}' failed or no response.")
        else: # suitable node was itself, or no other node found
             print(f"Node B will run general task '{general_task.task_id}' locally (or no other node found).")
             await node_b.local_vcpu.submit_task(general_task)
             local_res = await node_b.local_vcpu.get_task_result(general_task.task_id, wait_timeout_sec=5.0)
             print(f"  Node B local result for general task: {local_res.status.value if local_res else 'Timeout/Error'}")


    # Cleanup
    await vcpu_a.stop(graceful=False)
    await vcpu_b.stop(graceful=False)
    print("\nFederation demo finished.")

if __name__ == "__main__":
    import asyncio
    import random # For find_suitable_node_for_task example
    asyncio.run(main_federation_demo())
