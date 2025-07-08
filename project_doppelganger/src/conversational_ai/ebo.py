from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional, Tuple

from project_doppelganger.src.persona_modeling.behavioral_model import (
    PersonalityTrait, TraitScore, Emotion, CurrentEmotionalState
)

# --- EBO Input and Output Structures ---

@dataclass
class EBOInput:
    """
    Input data for the EchoSphere Behavioral Orchestrator.
    """
    user_sentiment: Dict[str, float] = field(default_factory=dict) # e.g., {"positive": 0.8, "negative": 0.1}
    conversation_topic: Optional[str] = None # Extracted by Minimizer or other upstream component
    persona_current_emotion: CurrentEmotionalState = field(default_factory=CurrentEmotionalState)
    persona_traits: Dict[PersonalityTrait, TraitScore] = field(default_factory=dict) # Key traits relevant to convo

    # Conceptual input from AI-vCPU's Context Specific Layer (CSL) or other monitoring
    introspection_status: Dict[str, Any] = field(default_factory=dict) # e.g., {"cognitive_load": "low", "goal_achieved": False}

    # Other contextual flags
    is_new_conversation: bool = True
    user_direct_request_type: Optional[str] = None # e.g., "question", "command", "statement"
    previous_ebo_output: Optional["EBOOutput"] = None # For continuity or chaining rules


@dataclass
class EBOOutput:
    """
    Output directive from the EchoSphere Behavioral Orchestrator.
    This guides the LLM prompt generation.
    """
    action_request: str # e.g., "generate_empathetic_response", "answer_question_directly", "share_opinion"
    interaction_goal: str # e.g., "build_rapport", "provide_information", "deflect_topic"
    context_modifiers: Dict[str, Any] = field(default_factory=dict)
    # Examples for context_modifiers:
    #   "llm_temperature_modifier": -0.2 (be less random)
    #   "response_length_hint": "concise" / "detailed"
    #   "emotional_tone_hint": "empathetic" / "formal" / "humorous"
    #   "knowledge_domain_focus": "persona_expertise_area_1"
    #   "force_intro_prompt": True (e.g. for new conversations)
    matched_rule_id: Optional[str] = None
    confidence: float = 1.0 # Confidence in this directive

# --- EBO Rule Definition ---

@dataclass
class EBORule:
    """
    Defines a single rule for the EBO.
    """
    rule_id: str
    description: str
    priority: int # Higher number = higher priority

    # Conditions: A list of functions that take EBOInput and return True if condition met.
    # More complex conditions can be lambdas or dedicated functions.
    conditions: List[Callable[[EBOInput], bool]]

    # Output to generate if all conditions are met
    output_template: EBOOutput

    def evaluate(self, ebo_input: EBOInput) -> bool:
        """Checks if all conditions for this rule are met given the input."""
        if not self.conditions: # A rule with no conditions always matches (if used carefully)
            return True
        try:
            return all(condition(ebo_input) for condition in self.conditions)
        except Exception as e:
            # print(f"Error evaluating condition for rule {self.rule_id}: {e}") # Log this
            return False

# --- EBO Engine ---

class EBO:
    """
    EchoSphere Behavioral Orchestrator (EBO).
    A rules engine that translates persona state and user input into LLM directives.
    """
    def __init__(self, rules: Optional[List[EBORule]] = None):
        self.rules: List[EBORule] = sorted(rules if rules else [], key=lambda r: r.priority, reverse=True)

    def add_rule(self, rule: EBORule):
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    def process(self, ebo_input: EBOInput) -> EBOOutput:
        """
        Processes the input through the rules engine and returns the first matching rule's output.
        """
        for rule in self.rules:
            if rule.evaluate(ebo_input):
                # "Instantiate" the output from the template, potentially modifying it further if needed
                # For now, just copy. A more advanced system might allow dynamic values in the template.
                final_output = EBOOutput(
                    action_request=rule.output_template.action_request,
                    interaction_goal=rule.output_template.interaction_goal,
                    context_modifiers=rule.output_template.context_modifiers.copy(), # Ensure dict is copied
                    matched_rule_id=rule.rule_id,
                    confidence=rule.output_template.confidence
                )
                return final_output

        # Default output if no rules match
        return EBOOutput(
            action_request="generate_standard_response",
            interaction_goal="maintain_conversation",
            context_modifiers={"emotional_tone_hint": "neutral"},
            matched_rule_id="DEFAULT_FALLBACK",
            confidence=0.5
        )

# --- Example Rule Definitions and Usage (for demonstration) ---

def example_rules() -> List[EBORule]:
    rules = []

    # Rule 1: Greeting on new conversation
    rules.append(EBORule(
        rule_id="GREET_NEW_CONVO",
        description="Standard greeting if it's a new conversation.",
        priority=100,
        conditions=[lambda i: i.is_new_conversation],
        output_template=EBOOutput(
            action_request="generate_greeting",
            interaction_goal="initiate_positive_interaction",
            context_modifiers={"response_length_hint": "short", "force_intro_prompt": True}
        )
    ))

    # Rule 2: Empathetic response if user is sad and persona is agreeable
    rules.append(EBORule(
        rule_id="EMPATHY_IF_USER_SAD_AGREEABLE_PERSONA",
        description="Show empathy if user is sad and persona is agreeable.",
        priority=90,
        conditions=[
            lambda i: (i.user_sentiment.get("negative", 0) > 0.6 and
                       i.user_sentiment.get("negative",0) > i.user_sentiment.get("positive",0)), # User predominantly negative/sad
            lambda i: (i.persona_traits.get(PersonalityTrait.AGREEABLENESS, TraitScore(0)).value > 0.6) # Persona is agreeable
        ],
        output_template=EBOOutput(
            action_request="generate_empathetic_response",
            interaction_goal="show_support_and_build_rapport",
            context_modifiers={"emotional_tone_hint": "empathetic", "response_length_hint": "medium"}
        )
    ))

    # Rule 3: Humorous response if persona is humorous and user is neutral/positive
    rules.append(EBORule(
        rule_id="HUMOR_IF_PERSONA_HUMOROUS_USER_POSITIVE",
        description="Attempt humor if persona is humorous and user is in a good mood.",
        priority=80,
        conditions=[
            lambda i: i.persona_traits.get(PersonalityTrait.HUMOROUSNESS, TraitScore(0)).value > 0.7,
            lambda i: i.user_sentiment.get("positive", 0) > 0.5 or i.user_sentiment.get("negative", 0) < 0.3
        ],
        output_template=EBOOutput(
            action_request="generate_lighthearted_or_humorous_response",
            interaction_goal="entertain_or_build_rapport",
            context_modifiers={"emotional_tone_hint": "humorous", "llm_temperature_modifier": 0.1} # Slightly more creative
        )
    ))

    # Rule 4: Direct answer if user asks a question and persona is conscientious
    rules.append(EBORule(
        rule_id="DIRECT_ANSWER_IF_QUESTION_CONSCIENTIOUS_PERSONA",
        description="Provide a direct answer if user asks a question and persona is conscientious.",
        priority=85,
        conditions=[
            lambda i: i.user_direct_request_type == "question",
            lambda i: i.persona_traits.get(PersonalityTrait.CONSCIENTIOUSNESS, TraitScore(0)).value > 0.6
        ],
        output_template=EBOOutput(
            action_request="answer_question_factually",
            interaction_goal="provide_information",
            context_modifiers={"response_length_hint": "concise_but_complete", "knowledge_domain_focus": "relevant_to_question"}
        )
    ))

    # Rule 5: Persona is feeling ANXIOUS and user sentiment is negative, deflect or be cautious
    rules.append(EBORule(
        rule_id="CAUTIOUS_RESPONSE_IF_PERSONA_ANXIOUS_USER_NEGATIVE",
        description="Be cautious or deflect if persona is anxious and user is negative.",
        priority=95,
        conditions=[
            lambda i: i.persona_current_emotion.dominant_emotion == Emotion.ANXIOUS and i.persona_current_emotion.intensity > 0.6,
            lambda i: i.user_sentiment.get("negative", 0) > 0.5
        ],
        output_template=EBOOutput(
            action_request="generate_cautious_or_deflecting_response",
            interaction_goal="avoid_escalation_or_maintain_stability",
            context_modifiers={"emotional_tone_hint": "neutral_cautious", "response_length_hint": "short"}
        )
    ))

    return rules


if __name__ == "__main__":
    ebo_engine = EBO(rules=example_rules())

    # --- Test Scenario 1: New conversation ---
    print("\n--- Scenario 1: New Conversation ---")
    input1 = EBOInput(is_new_conversation=True)
    output1 = ebo_engine.process(input1)
    print(f"Input: {input1}")
    print(f"Output: {output1}")
    assert output1.matched_rule_id == "GREET_NEW_CONVO"

    # --- Test Scenario 2: User sad, agreeable persona ---
    print("\n--- Scenario 2: User Sad, Agreeable Persona ---")
    agreeable_traits = {PersonalityTrait.AGREEABLENESS: TraitScore(0.8)}
    input2 = EBOInput(
        is_new_conversation=False,
        user_sentiment={"negative": 0.7, "positive": 0.1},
        persona_traits=agreeable_traits
    )
    output2 = ebo_engine.process(input2)
    print(f"Input: {input2}")
    print(f"Output: {output2}")
    assert output2.matched_rule_id == "EMPATHY_IF_USER_SAD_AGREEABLE_PERSONA"

    # --- Test Scenario 3: Humorous persona, user positive ---
    print("\n--- Scenario 3: Humorous Persona, User Positive ---")
    humorous_traits = {PersonalityTrait.HUMOROUSNESS: TraitScore(0.9)}
    input3 = EBOInput(
        is_new_conversation=False,
        user_sentiment={"positive": 0.8, "negative": 0.1},
        persona_traits=humorous_traits
    )
    output3 = ebo_engine.process(input3)
    print(f"Input: {input3}")
    print(f"Output: {output3}")
    assert output3.matched_rule_id == "HUMOR_IF_PERSONA_HUMOROUS_USER_POSITIVE"

    # --- Test Scenario 4: Question from user, conscientious persona ---
    print("\n--- Scenario 4: User Question, Conscientious Persona ---")
    conscientious_traits = {PersonalityTrait.CONSCIENTIOUSNESS: TraitScore(0.7)}
    input4 = EBOInput(
        is_new_conversation=False,
        user_direct_request_type="question",
        persona_traits=conscientious_traits
    )
    output4 = ebo_engine.process(input4)
    print(f"Input: {input4}")
    print(f"Output: {output4}")
    assert output4.matched_rule_id == "DIRECT_ANSWER_IF_QUESTION_CONSCIENTIOUS_PERSONA"

    # --- Test Scenario 5: Persona anxious, user negative (higher priority than humor/direct answer) ---
    print("\n--- Scenario 5: Persona Anxious, User Negative ---")
    anxious_emotion = CurrentEmotionalState(dominant_emotion=Emotion.ANXIOUS, intensity=0.7)
    # Traits that might also match other rules if this one wasn't higher priority
    conflicting_traits = {
        PersonalityTrait.HUMOROUSNESS: TraitScore(0.9),
        PersonalityTrait.CONSCIENTIOUSNESS: TraitScore(0.7)
    }
    input5 = EBOInput(
        is_new_conversation=False,
        user_sentiment={"negative": 0.8, "positive": 0.1},
        user_direct_request_type="question", # Could match rule 4 if not for this higher prio one
        persona_current_emotion=anxious_emotion,
        persona_traits=conflicting_traits
    )
    output5 = ebo_engine.process(input5)
    print(f"Input: {input5}")
    print(f"Output: {output5}")
    assert output5.matched_rule_id == "CAUTIOUS_RESPONSE_IF_PERSONA_ANXIOUS_USER_NEGATIVE"

    # --- Test Scenario 6: No specific rule matches ---
    print("\n--- Scenario 6: Default Fallback ---")
    input6 = EBOInput(
        is_new_conversation=False,
        user_sentiment={"neutral": 0.9} # Generic input unlikely to hit specific rules
    )
    output6 = ebo_engine.process(input6)
    print(f"Input: {input6}")
    print(f"Output: {output6}")
    assert output6.matched_rule_id == "DEFAULT_FALLBACK"

    print("\nEBO example run finished.")
