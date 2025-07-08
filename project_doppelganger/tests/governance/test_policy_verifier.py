import unittest
import time
from typing import Tuple, Optional, List

from project_doppelganger.src.governance.policy_verifier import (
    PolicyVerifier,
    MTLProperty,
    BehavioralTrace,
    StateObservation,
    VerificationResult,
    PolicyViolation
)

# --- Re-usable Mock MTL Property Callables for Testing ---
def mock_prop_always_true(trace: BehavioralTrace) -> Tuple[bool, Optional[StateObservation]]:
    return True, None

def mock_prop_always_false(trace: BehavioralTrace) -> Tuple[bool, Optional[StateObservation]]:
    # Returns the first observation as the "violating" one if trace is not empty
    return False, trace.observations[0] if trace.observations else None

def mock_prop_violates_on_specific_flag(flag_name: str, flag_value: Any):
    def checker(trace: BehavioralTrace) -> Tuple[bool, Optional[StateObservation]]:
        for obs in trace.observations:
            if obs.custom_flags.get(flag_name) == flag_value:
                return False, obs
        return True, None
    return checker

class TestPolicyVerifier(unittest.TestCase):

    def setUp(self):
        self.properties: List[MTLProperty] = [
            MTLProperty(
                property_id="P_TRUE", description="Always True Property",
                formula_callable=mock_prop_always_true
            ),
            MTLProperty(
                property_id="P_FALSE", description="Always False Property",
                formula_callable=mock_prop_always_false
            ),
            MTLProperty(
                property_id="P_NO_BAD_FLAG", description="No 'bad_flag: True'",
                formula_callable=mock_prop_violates_on_specific_flag("bad_flag", True)
            ),
            MTLProperty( # String-only property for conceptual check
                property_id="P_STRING_CONCEPTUAL_PASS", description="String only, conceptual pass",
                mtl_formula_str="G (some_condition)"
            ),
             MTLProperty( # String-only property that will "fail" conceptually
                property_id="P_STRING_CONCEPTUAL_FAIL", description="String only, conceptual fail",
                mtl_formula_str="G (another_condition CONCEPTUAL_FAIL)"
            )
        ]
        self.verifier = PolicyVerifier(properties=self.properties)

    def test_verifier_initialization(self):
        self.assertEqual(len(self.verifier.properties_to_verify), 5)
        self.assertEqual(self.verifier.properties_to_verify[0].property_id, "P_TRUE") # Assuming order is preserved

    def test_add_property(self):
        new_prop = MTLProperty("P_NEW", "A new test property", formula_callable=mock_prop_always_true)
        initial_count = len(self.verifier.properties_to_verify)
        self.verifier.add_property(new_prop)
        self.assertEqual(len(self.verifier.properties_to_verify), initial_count + 1)
        self.assertEqual(self.verifier.properties_to_verify[-1].property_id, "P_NEW")

    def test_verify_empty_trace(self):
        empty_trace = BehavioralTrace(trace_id="empty_t", persona_id="p1")
        result = self.verifier.verify_behavioral_trace(empty_trace)
        self.assertIsInstance(result, VerificationResult)
        self.assertEqual(len(result.violations_found), 0) # No observations, so no callable violations
        self.assertTrue(result.passed_all) # No violations means passed_all is true

    def test_verify_trace_all_callable_properties_hold(self):
        compliant_trace = BehavioralTrace(trace_id="compliant_t", persona_id="p1")
        compliant_trace.add_observation(StateObservation(custom_flags={"bad_flag": False}))
        compliant_trace.add_observation(StateObservation(custom_flags={"good_flag": True}))

        # Temporarily remove properties that would fail or are string-only for this specific test
        original_props = self.verifier.properties_to_verify
        self.verifier.properties_to_verify = [
            p for p in original_props if p.property_id in ["P_TRUE", "P_NO_BAD_FLAG"]
        ]

        result = self.verifier.verify_behavioral_trace(compliant_trace)

        self.assertEqual(len(result.violations_found), 0, f"Violations found: {result.violations_found}")
        self.assertTrue(result.passed_all)
        self.assertEqual(len(result.properties_checked), 2)

        self.verifier.properties_to_verify = original_props # Restore

    def test_verify_trace_one_callable_property_fails(self):
        violating_trace = BehavioralTrace(trace_id="violating_t_bad_flag", persona_id="p1")
        violating_obs = StateObservation(custom_flags={"bad_flag": True})
        violating_trace.add_observation(StateObservation(custom_flags={"bad_flag": False}))
        violating_trace.add_observation(violating_obs) # This will violate P_NO_BAD_FLAG

        original_props = self.verifier.properties_to_verify
        # Test only with P_TRUE and P_NO_BAD_FLAG for clarity
        self.verifier.properties_to_verify = [
            p for p in original_props if p.property_id in ["P_TRUE", "P_NO_BAD_FLAG"]
        ]

        result = self.verifier.verify_behavioral_trace(violating_trace)

        self.assertEqual(len(result.violations_found), 1)
        self.assertFalse(result.passed_all)
        violation = result.violations_found[0]
        self.assertEqual(violation.property_violated.property_id, "P_NO_BAD_FLAG")
        self.assertEqual(violation.violating_observation, violating_obs)

        self.verifier.properties_to_verify = original_props # Restore

    def test_verify_trace_always_false_property(self):
        trace_with_obs = BehavioralTrace(trace_id="t_for_false_prop", persona_id="p1")
        obs1 = StateObservation()
        trace_with_obs.add_observation(obs1)

        original_props = self.verifier.properties_to_verify
        self.verifier.properties_to_verify = [
            p for p in original_props if p.property_id == "P_FALSE"
        ] # Only test P_FALSE

        result = self.verifier.verify_behavioral_trace(trace_with_obs)

        self.assertEqual(len(result.violations_found), 1)
        self.assertEqual(result.violations_found[0].property_violated.property_id, "P_FALSE")
        self.assertEqual(result.violations_found[0].violating_observation, obs1)

        self.verifier.properties_to_verify = original_props # Restore

    def test_verify_string_only_conceptual_properties(self):
        trace = BehavioralTrace(trace_id="t_string_props", persona_id="p1")
        trace.add_observation(StateObservation()) # Needs at least one observation

        # Using the full default set of properties from setUp
        result = self.verifier.verify_behavioral_trace(trace)

        # Expected violations:
        # 1. P_FALSE (callable)
        # 2. P_STRING_CONCEPTUAL_FAIL (string-based conceptual)
        self.assertEqual(len(result.violations_found), 2)

        found_p_false = any(v.property_violated.property_id == "P_FALSE" for v in result.violations_found)
        found_p_string_fail = any(v.property_violated.property_id == "P_STRING_CONCEPTUAL_FAIL" for v in result.violations_found)

        self.assertTrue(found_p_false, "P_FALSE violation not found")
        self.assertTrue(found_p_string_fail, "P_STRING_CONCEPTUAL_FAIL violation not found")

        # Check that P_STRING_CONCEPTUAL_PASS did not cause a violation
        found_p_string_pass_violation = any(v.property_violated.property_id == "P_STRING_CONCEPTUAL_PASS" for v in result.violations_found)
        self.assertFalse(found_p_string_pass_violation, "P_STRING_CONCEPTUAL_PASS should not have caused a violation")

    def test_verification_result_structure(self):
        trace = BehavioralTrace(trace_id="t_res_struct", persona_id="p1")
        trace.add_observation(StateObservation())
        result = self.verifier.verify_behavioral_trace(trace)

        self.assertIsNotNone(result.timestamp)
        self.assertEqual(len(result.properties_checked), len(self.properties))
        self.assertIsNotNone(result.model_checker_log)
        self.assertTrue("Simulated verification completed" in result.model_checker_log)


if __name__ == '__main__':
    unittest.main()
