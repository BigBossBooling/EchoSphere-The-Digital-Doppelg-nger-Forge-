import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from project_doppelganger.src.network.federation_protocol import (
    FederationManager,
    FederationNode,
    FederatedTaskRequest,
    FederatedTaskResponse
)
from project_doppelganger.src.ai_vcpu_core import (
    AIVCPU, AIVCPUConfig, TaskRequest, TaskResult, TaskStatus, TaskPriority, CoreType
)

class TestFederationProtocolConceptual(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.manager = FederationManager()

        # Create two mock AIVCPU instances
        self.vcpu_config1 = AIVCPUConfig(num_general_cores=1, default_language_modeler_cores=1)
        self.mock_vcpu1 = AIVCPU(config=self.vcpu_config1) # Use real AIVCPU for internal logic
        await self.mock_vcpu1.start()

        self.vcpu_config2 = AIVCPUConfig(num_general_cores=2)
        self.mock_vcpu2 = AIVCPU(config=self.vcpu_config2)
        await self.mock_vcpu2.start()

        self.node1 = FederationNode(node_id="Node1", local_vcpu=self.mock_vcpu1, federation_manager=self.manager)
        self.node2 = FederationNode(node_id="Node2", local_vcpu=self.mock_vcpu2, federation_manager=self.manager)

        self.manager.register_node(self.node1)
        self.manager.register_node(self.node2)

    async def asyncTearDown(self):
        if self.mock_vcpu1._is_running:
            await self.mock_vcpu1.stop(graceful=False)
        if self.mock_vcpu2._is_running:
            await self.mock_vcpu2.stop(graceful=False)
        # Clear manager's nodes if needed, though new manager is created per test method by default if setUp is per method
        self.manager.nodes.clear()


    async def test_register_unregister_node(self):
        self.assertIn("Node1", self.manager.nodes)
        self.assertIn("Node2", self.manager.nodes)

        self.manager.unregister_node("Node1")
        self.assertNotIn("Node1", self.manager.nodes)
        self.assertIn("Node2", self.manager.nodes)

    async def test_node_send_federated_task_request_and_receive_response(self):
        task_to_offload = TaskRequest(
            instruction="test_instruction_for_node2",
            data={"payload": "data for node2"},
            priority=TaskPriority.MEDIUM,
            complexity=2
        )

        # Node1 sends task to Node2
        federated_response = await self.node1.send_federated_task_request(
            task_to_offload,
            target_node_id="Node2"
        )

        self.assertIsNotNone(federated_response)
        self.assertIsInstance(federated_response, FederatedTaskResponse)
        self.assertEqual(federated_response.original_task_id, task_to_offload.task_id)
        self.assertEqual(federated_response.source_node_id, "Node2") # Response came from Node2
        self.assertEqual(federated_response.destination_node_id, "Node1")

        self.assertIsNotNone(federated_response.task_result)
        task_result = federated_response.task_result
        self.assertEqual(task_result.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(task_result.core_id_executed_on) # A core on Node2 should have run it
        # Check if the result data indicates processing by Node2's VCPU
        self.assertIn(f"processed by {CoreType.GENERAL_PURPOSE.value} Core", task_result.result_data["message"])


    async def test_federated_task_target_node_offline_or_not_found(self):
        task_to_offload = TaskRequest(instruction="task_for_offline_node")

        # Try sending to a non-existent node
        response_non_existent = await self.node1.send_federated_task_request(task_to_offload, "NodeNonExistent")
        self.assertIsNone(response_non_existent) # Manager route_request should return None

        # Try sending to an offline node (conceptually)
        self.node2.is_online = False
        response_offline = await self.node1.send_federated_task_request(task_to_offload, "Node2")
        self.assertIsNone(response_offline) # Manager route_request should return None
        self.node2.is_online = True # Reset for other tests


    async def test_federated_task_processing_timeout_on_remote_node(self):
        # To simulate timeout, we need the local_vcpu.get_task_result on the remote node to return None.
        # This is hard to do without deeper mocking of AIVCPU's internal timing or its get_task_result.
        # The current FederationNode.receive_federated_task_request has a timeout of 10s for get_task_result.
        # We can make a task that takes longer than that conceptually.

        long_task = TaskRequest(
            instruction="very_long_task",
            complexity=1500, # Results in 15s sleep (1500 * 10ms)
            priority=TaskPriority.LOW
        )

        # Node1 sends task to Node2, Node2's get_task_result for this will timeout internally in receive_federated_task_request
        federated_response = await self.node1.send_federated_task_request(long_task, "Node2")

        self.assertIsNotNone(federated_response, "A response (even if error/timeout) should be received by Node1")
        self.assertIsInstance(federated_response, FederatedTaskResponse)
        self.assertEqual(federated_response.original_task_id, long_task.task_id)

        self.assertIsNotNone(federated_response.task_result)
        task_result = federated_response.task_result
        self.assertEqual(task_result.status, TaskStatus.FAILED) # Should be marked FAILED due to timeout on Node2
        self.assertIn(f"Processing timed out on federated node Node2", task_result.error_message)


    async def test_find_suitable_node_for_task_conceptual(self):
        # Node1 (1 GP, 1 LM), Node2 (2 GP)

        # Task requiring LM core
        lm_task_req = TaskRequest(required_core_type=CoreType.LANGUAGE_MODELER)
        suitable_node_for_lm = await self.manager.find_suitable_node_for_task(lm_task_req)
        # Node1 has an LM core. Node2 does not explicitly.
        # The logic in find_suitable_node_for_task also checks core status (IDLE).
        # Assuming Node1's LM core is idle:
        self.assertEqual(suitable_node_for_lm, "Node1")

        # Task requiring GP core (both nodes have GP cores)
        gp_task_req = TaskRequest(required_core_type=CoreType.GENERAL_PURPOSE)
        suitable_node_for_gp = await self.manager.find_suitable_node_for_task(gp_task_req)
        self.assertIn(suitable_node_for_gp, ["Node1", "Node2"]) # Could be either

        # Make Node1's LM core busy (conceptually)
        node1_lm_core = next(c for c in self.mock_vcpu1.cores if c.config.core_type == CoreType.LANGUAGE_MODELER)
        original_status_node1_lm = node1_lm_core.status
        node1_lm_core.status = "Busy" # CoreStatus.BUSY.value

        suitable_node_for_lm_busy = await self.manager.find_suitable_node_for_task(lm_task_req)
        # Node1's LM core is busy, so it should not be selected if find_suitable checks idle status.
        # The current find_suitable_node_for_task checks this.
        self.assertIsNone(suitable_node_for_lm_busy, "Should not find Node1 if its LM core is busy and Node2 has no LM core.")

        node1_lm_core.status = original_status_node1_lm # Reset status

        # Test with no specific requirement (should pick one of them)
        generic_task_req = TaskRequest(instruction="any_task")
        suitable_node_generic = await self.manager.find_suitable_node_for_task(generic_task_req)
        self.assertIn(suitable_node_generic, ["Node1", "Node2"])


if __name__ == '__main__':
    unittest.main()
