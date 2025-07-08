import unittest
from project_doppelganger.src.conversational_ai.ebo import (
    EBO, EBORule, EBOInput, EBOOutput
)
from project_doppelganger.src.persona_modeling.behavioral_model import (
    PersonalityTrait, TraitScore, Emotion, CurrentEmotionalState
)

# --- Helper: Define a set of reusable test rules ---
def get_test_rules() -> list[EBORule]:
    return [
        EBORule(
            rule_id="TEST_R001_NEW_CONVO", priority=100, description="Greet new convo",
            conditions=[lambda i: i.is_new_conversation],
            output_template=EBOOutput(action_request="greet", interaction_goal="initiate", matched_rule_id="TEST_R001_NEW_CONVO")
        ),
        EBORule(
            rule_id="TEST_R002_USER_HAPPY_PERSONA_EXTROVERT", priority=90, description="User happy, persona extrovert",
            conditions=[
                lambda i: i.user_sentiment.get("positive", 0) > 0.7,
                lambda i: i.persona_traits.get(PersonalityTrait.EXTRAVERSION, TraitScore(0)).value > 0.6
            ],
            output_template=EBOOutput(action_request="engage_energetically", interaction_goal="share_enthusiasm", matched_rule_id="TEST_R002_USER_HAPPY_PERSONA_EXTROVERT")
        ),
        EBORule(
            rule_id="TEST_R003_PERSONA_SAD", priority=95, description="Persona is sad",
            conditions=[lambda i: i.persona_current_emotion.dominant_emotion == Emotion.SAD and i.persona_current_emotion.intensity > 0.5],
            output_template=EBOOutput(action_request="express_sadness_subtly", interaction_goal="seek_comfort_or_be_reserved", matched_rule_id="TEST_R003_PERSONA_SAD")
        ),
        EBORule(
            rule_id="TEST_R004_USER_ASKS_QUESTION", priority=80, description="User asks a question",
            conditions=[lambda i: i.user_direct_request_type == "question"],
            output_template=EBOOutput(action_request="answer_question", interaction_goal="inform", matched_rule_id="TEST_R004_USER_ASKS_QUESTION")
        ),
        EBORule( # Catch-all if specific conditions for question not met
            rule_id="TEST_R005_USER_ASKS_QUESTION_LOW_PRIO", priority=10, description="User asks a question (low prio)",
            conditions=[lambda i: i.user_direct_request_type == "question"],
            output_template=EBOOutput(action_request="answer_question_generically", interaction_goal="inform_low_prio", matched_rule_id="TEST_R005_USER_ASKS_QUESTION_LOW_PRIO")
        ),
         EBORule(
            rule_id="TEST_R006_INTROSPECTION_HIGH_LOAD", priority=110, description="Introspection: high cognitive load",
            conditions=[lambda i: i.introspection_status.get("cognitive_load") == "high"],
            output_template=EBOOutput(action_request="simplify_response", interaction_goal="reduce_cognitive_load", matched_rule_id="TEST_R006_INTROSPECTION_HIGH_LOAD")
        )
    ]

class TestEBO(unittest.TestCase):

    def setUp(self):
        self.ebo = EBO(rules=get_test_rules())
        self.default_input_params = {
            "user_sentiment": {"neutral": 1.0},
            "conversation_topic": "general",
            "persona_current_emotion": CurrentEmotionalState(),
            "persona_traits": {},
            "introspection_status": {},
            "is_new_conversation": False,
            "user_direct_request_type": None,
            "previous_ebo_output": None
        }

    def _create_input(self, **kwargs) -> EBOInput:
        """Helper to create EBOInput, overriding defaults with kwargs."""
        params = {**self.default_input_params, **kwargs}
        # Ensure complex objects are deep copied if they are mutable and modified by default
        params["persona_current_emotion"] = params["persona_current_emotion"] if "persona_current_emotion" in kwargs else CurrentEmotionalState()
        params["persona_traits"] = params["persona_traits"] if "persona_traits" in kwargs else {}
        params["user_sentiment"] = params["user_sentiment"] if "user_sentiment" in kwargs else {"neutral": 1.0}
        params["introspection_status"] = params["introspection_status"] if "introspection_status" in kwargs else {}
        return EBOInput(**params)

    def test_rule_evaluation_simple_true(self):
        rule = EBORule("t1", "", 1, [lambda i: True, lambda i: 1 == 1], EBOOutput("a", "b"))
        self.assertTrue(rule.evaluate(self._create_input()))

    def test_rule_evaluation_simple_false(self):
        rule = EBORule("t2", "", 1, [lambda i: True, lambda i: 1 == 0], EBOOutput("a", "b"))
        self.assertFalse(rule.evaluate(self._create_input()))

    def test_rule_evaluation_condition_error(self):
        def error_condition(i: EBOInput):
            raise ValueError("Test error in condition")
        rule = EBORule("t_err", "", 1, [error_condition], EBOOutput("a","b"))
        self.assertFalse(rule.evaluate(self._create_input())) # Should catch error and return False

    def test_process_new_conversation_rule(self):
        ebo_input = self._create_input(is_new_conversation=True)
        result = self.ebo.process(ebo_input)
        self.assertEqual(result.matched_rule_id, "TEST_R001_NEW_CONVO")
        self.assertEqual(result.action_request, "greet")

    def test_process_user_happy_extrovert_persona_rule(self):
        traits = {PersonalityTrait.EXTRAVERSION: TraitScore(0.7)}
        ebo_input = self._create_input(user_sentiment={"positive": 0.8}, persona_traits=traits)
        result = self.ebo.process(ebo_input)
        self.assertEqual(result.matched_rule_id, "TEST_R002_USER_HAPPY_PERSONA_EXTROVERT")

    def test_process_persona_sad_rule(self):
        sad_emotion = CurrentEmotionalState(dominant_emotion=Emotion.SAD, intensity=0.7)
        ebo_input = self._create_input(persona_current_emotion=sad_emotion)
        result = self.ebo.process(ebo_input)
        self.assertEqual(result.matched_rule_id, "TEST_R003_PERSONA_SAD")
        self.assertEqual(result.action_request, "express_sadness_subtly")

    def test_process_introspection_high_load_highest_priority(self):
        # This rule (TEST_R006) has priority 110, higher than TEST_R001_NEW_CONVO (100)
        ebo_input = self._create_input(
            is_new_conversation=True, # Would match TEST_R001
            introspection_status={"cognitive_load": "high"} # But this matches higher priority TEST_R006
        )
        result = self.ebo.process(ebo_input)
        self.assertEqual(result.matched_rule_id, "TEST_R006_INTROSPECTION_HIGH_LOAD")
        self.assertEqual(result.action_request, "simplify_response")


    def test_process_user_asks_question_rule(self):
        ebo_input = self._create_input(user_direct_request_type="question")
        # Should match R004 (priority 80) over R005 (priority 10)
        result = self.ebo.process(ebo_input)
        self.assertEqual(result.matched_rule_id, "TEST_R004_USER_ASKS_QUESTION")

    def test_process_default_fallback(self):
        # Input that doesn't match any specific rule
        ebo_input = self._create_input(user_sentiment={"neutral": 0.5}, conversation_topic="obscure")
        result = self.ebo.process(ebo_input)
        self.assertEqual(result.matched_rule_id, "DEFAULT_FALLBACK")
        self.assertEqual(result.action_request, "generate_standard_response")
        self.assertEqual(result.confidence, 0.5)

    def test_add_rule_maintains_priority_order(self):
        new_rule_mid_prio = EBORule(
            rule_id="NEW_RULE_MID_PRIO", priority=92, description="A new rule inserted",
            conditions=[lambda i: i.conversation_topic == "specific_topic_for_new_rule"],
            output_template=EBOOutput(action_request="handle_specific_topic", interaction_goal="topical_discussion", matched_rule_id="NEW_RULE_MID_PRIO")
        )
        self.ebo.add_rule(new_rule_mid_prio)

        # Check if it's inserted correctly based on priority
        # Priorities: 110, 100, [95], 92 (new), 90, 80, 10
        self.assertEqual(self.ebo.rules[2].rule_id, "TEST_R003_PERSONA_SAD") # Priority 95
        self.assertEqual(self.ebo.rules[3].rule_id, "NEW_RULE_MID_PRIO")     # Priority 92 (new)
        self.assertEqual(self.ebo.rules[4].rule_id, "TEST_R002_USER_HAPPY_PERSONA_EXTROVERT") # Priority 90

        # Test if the new rule is matched
        ebo_input = self._create_input(conversation_topic="specific_topic_for_new_rule")
        result = self.ebo.process(ebo_input)
        self.assertEqual(result.matched_rule_id, "NEW_RULE_MID_PRIO")

    def test_rule_with_no_conditions(self):
        # A rule with no conditions should always match if it's the highest priority or no other rule matches first.
        rule_no_cond = EBORule(
            rule_id="NO_COND_RULE", priority=1000, # Highest priority
            description="Always matches", conditions=[],
            output_template=EBOOutput("no_cond_action", "no_cond_goal", matched_rule_id="NO_COND_RULE")
        )
        self.ebo.add_rule(rule_no_cond)
        ebo_input = self._create_input() # Any input
        result = self.ebo.process(ebo_input)
        self.assertEqual(result.matched_rule_id, "NO_COND_RULE")


if __name__ == '__main__':
    unittest.main()
