from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple

# --- Enums and Supporting Dataclasses for Personality Aspects ---

class PersonalityTrait(Enum):
    # Simplified Big Five model + others relevant to communication
    OPENNESS = "Openness" # (inventive/curious vs. consistent/cautious)
    CONSCIENTIOUSNESS = "Conscientiousness" # (efficient/organized vs. easy-going/careless)
    EXTRAVERSION = "Extraversion" # (outgoing/energetic vs. solitary/reserved)
    AGREEABLENESS = "Agreeableness" # (friendly/compassionate vs. challenging/detached)
    NEUROTICISM = "Neuroticism" # (sensitive/nervous vs. secure/confident)

    FORMALITY = "Formality" # (formal vs. informal language)
    HUMOROUSNESS = "Humorousness" # (tendency to use humor)
    ASSERTIVENESS = "Assertiveness" # (directness in communication)
    EMPATHY_LEVEL = "EmpathyLevel" # (expressed empathy)
    VERBOSITY = "Verbosity" # (concise vs. talkative)

class Emotion(Enum):
    # Basic emotional states
    NEUTRAL = "Neutral"
    HAPPY = "Happy"
    SAD = "Sad"
    ANGRY = "Angry"
    SURPRISED = "Surprised"
    FEARFUL = "Fearful"
    DISGUSTED = "Disgusted"
    # More nuanced states could be added
    CURIOUS = "Curious"
    CONFIDENT = "Confident"
    ANXIOUS = "Anxious"

class CommunicationStyleAspect(Enum):
    TONE = "Tone" # e.g., Optimistic, Pessimistic, Sarcastic, Encouraging
    PACE = "Pace" # e.g., Fast, Medium, Slow (for spoken interaction primarily)
    LEXICAL_DIVERSITY = "LexicalDiversity" # Range of vocabulary
    SENTENCE_COMPLEXITY = "SentenceComplexity" # Simple vs. complex sentences
    PREFERRED_PHRASES = "PreferredPhrases" # Common idioms or sayings
    AVOIDED_TOPICS = "AvoidedTopics" # Topics the persona might steer clear of

@dataclass
class TraitScore:
    value: float # Typically normalized, e.g., 0.0 to 1.0, or -1.0 to 1.0 for bipolar traits
    confidence: float = 1.0 # Confidence in this score (0.0 to 1.0)

@dataclass
class CurrentEmotionalState:
    dominant_emotion: Emotion = Emotion.NEUTRAL
    intensity: float = 0.5 # Normalized 0.0 to 1.0
    secondary_emotions: Dict[Emotion, float] = field(default_factory=dict) # Emotion -> intensity

@dataclass
class CommunicationStyleProfile:
    aspects: Dict[CommunicationStyleAspect, Any] = field(default_factory=dict)
    # Example: aspects[CommunicationStyleAspect.TONE] = "Optimistic"
    # aspects[CommunicationStyleAspect.PREFERRED_PHRASES] = ["No worries!", "Absolutely!"]

# --- Main Behavioral Model ---

@dataclass
class BehavioralModel:
    """
    Represents the learned personality and behavioral patterns of a doppelganger.
    """
    persona_id: str
    base_traits: Dict[PersonalityTrait, TraitScore] = field(default_factory=dict)
    current_emotion: CurrentEmotionalState = field(default_factory=CurrentEmotionalState)
    communication_style: CommunicationStyleProfile = field(default_factory=CommunicationStyleProfile)

    # Conceptual: Learned decision heuristics or preferences
    decision_biases: Dict[str, Any] = field(default_factory=dict) # e.g., "optimism_bias": 0.6

    # Conceptual: Knowledge graph summary or key facts known by persona (pointers, not full data)
    knowledge_summary: Dict[str, str] = field(default_factory=dict)

    # Conceptual: Neuroplasticity - how much the model adapts
    adaptability_level: float = 0.5 # 0.0 (static) to 1.0 (highly adaptive)
    last_updated_timestamp: float = field(default_factory=time.time)
    version: int = 1

    def update_trait(self, trait: PersonalityTrait, new_value: float, new_confidence: Optional[float] = None):
        if trait in self.base_traits:
            current_score = self.base_traits[trait]
            # Simple weighted average for updating, could be more sophisticated
            # Factor in adaptability: higher adaptability = new value has more weight
            weight_new = new_confidence if new_confidence is not None else 0.5
            weight_new *= (0.5 + self.adaptability_level) # Scale weight by adaptability

            current_score.value = (current_score.value * current_score.confidence * (1-weight_new) + \
                                   new_value * weight_new) / \
                                  (current_score.confidence * (1-weight_new) + weight_new + 1e-6) # Avoid div by zero

            if new_confidence is not None:
                current_score.confidence = (current_score.confidence + new_confidence) / 2 # Simplistic confidence update
                current_score.confidence = min(1.0, max(0.0, current_score.confidence)) # Clamp
        else:
            self.base_traits[trait] = TraitScore(value=new_value, confidence=new_confidence or 0.5)

        self._increment_version()

    def update_emotion(self, new_emotion: Emotion, new_intensity: float,
                       secondary: Optional[Dict[Emotion, float]] = None):
        # More complex emotional dynamics could be modeled here (e.g., decay, transitions)
        self.current_emotion.dominant_emotion = new_emotion
        self.current_emotion.intensity = min(1.0, max(0.0, new_intensity))
        if secondary:
            self.current_emotion.secondary_emotions = {e: min(1.0, max(0.0, i)) for e,i in secondary.items()}
        self._increment_version()

    def update_communication_aspect(self, aspect: CommunicationStyleAspect, value: Any):
        self.communication_style.aspects[aspect] = value
        self._increment_version()

    def add_preferred_phrase(self, phrase: str):
        phrases = self.communication_style.aspects.get(CommunicationStyleAspect.PREFERRED_PHRASES, [])
        if phrase not in phrases:
            phrases.append(phrase)
            self.communication_style.aspects[CommunicationStyleAspect.PREFERRED_PHRASES] = phrases
            self._increment_version()

    def _increment_version(self):
        self.version += 1
        self.last_updated_timestamp = time.time()

    def get_trait_value(self, trait: PersonalityTrait) -> Optional[float]:
        return self.base_traits[trait].value if trait in self.base_traits else None

    def get_dominant_emotion(self) -> Tuple[Emotion, float]:
        return self.current_emotion.dominant_emotion, self.current_emotion.intensity

    def get_communication_aspect(self, aspect: CommunicationStyleAspect) -> Any:
        return self.communication_style.aspects.get(aspect)

    def simulate_neuroplasticity_on_experience(self, experience_type: str, data: Dict[str, Any]):
        """
        Conceptual update based on a new 'experience'.
        This would involve complex logic, potentially calling out to an LLM or specific AI models
        via the AIVCPU to interpret the experience and suggest model updates.
        For now, it's a placeholder.
        """
        print(f"SIMULATING NEUROPLASTICITY: Persona {self.persona_id} had experience '{experience_type}'.")
        # Example: If experience was a conversation that went well (positive feedback)
        if experience_type == "positive_interaction_feedback":
            # Slightly increase agreeableness or a relevant positive trait
            current_agreeableness = self.get_trait_value(PersonalityTrait.AGREEABLENESS) or 0.5
            self.update_trait(PersonalityTrait.AGREEABLENESS, min(1.0, current_agreeableness + 0.05 * self.adaptability_level), 0.6)
            print(f"  Increased {PersonalityTrait.AGREEABLENESS.value} due to positive feedback.")

        elif experience_type == "learned_new_phrase" and "phrase" in data:
            self.add_preferred_phrase(data["phrase"])
            print(f"  Learned new phrase: {data['phrase']}")

        self._increment_version()


# Example Usage:
if __name__ == "__main__":
    import time

    model = BehavioralModel(persona_id="doppel_jane_001", adaptability_level=0.7)

    # Initialize some traits
    model.update_trait(PersonalityTrait.OPENNESS, 0.7, 0.8)
    model.update_trait(PersonalityTrait.EXTRAVERSION, 0.6, 0.9)
    model.update_trait(PersonalityTrait.FORMALITY, 0.3, 0.7) # More informal
    model.update_trait(PersonalityTrait.HUMOROUSNESS, 0.8, 0.6)

    # Set communication style
    model.update_communication_aspect(CommunicationStyleAspect.TONE, "Playful-Optimistic")
    model.add_preferred_phrase("You betcha!")
    model.add_preferred_phrase("Sounds like a plan.")

    # Set initial emotion
    model.update_emotion(Emotion.HAPPY, 0.7)

    print(f"--- Initial Model for {model.persona_id} (v{model.version}) ---")
    print(f"Openness: {model.get_trait_value(PersonalityTrait.OPENNESS):.2f}")
    print(f"Extraversion: {model.get_trait_value(PersonalityTrait.EXTRAVERSION):.2f}")
    print(f"Formality: {model.get_trait_value(PersonalityTrait.FORMALITY):.2f}")
    print(f"Humorousness: {model.get_trait_value(PersonalityTrait.HUMOROUSNESS):.2f}")
    print(f"Dominant Emotion: {model.get_dominant_emotion()[0].value} ({model.get_dominant_emotion()[1]:.2f})")
    print(f"Tone: {model.get_communication_aspect(CommunicationStyleAspect.TONE)}")
    print(f"Preferred Phrases: {model.get_communication_aspect(CommunicationStyleAspect.PREFERRED_PHRASES)}")

    # Simulate an experience
    print("\n--- Simulating Experience ---")
    model.simulate_neuroplasticity_on_experience(
        "positive_interaction_feedback",
        {"user_sentiment": "very_positive", "task_success": True}
    )
    model.simulate_neuroplasticity_on_experience(
        "learned_new_phrase",
        {"phrase": "No problemo!"}
    )

    # Change emotion based on an interaction
    model.update_emotion(Emotion.CURIOUS, 0.8, secondary_emotions={Emotion.HAPPY: 0.3})


    print(f"\n--- Updated Model for {model.persona_id} (v{model.version}) ---")
    print(f"Openness: {model.get_trait_value(PersonalityTrait.OPENNESS):.2f}")
    print(f"Extraversion: {model.get_trait_value(PersonalityTrait.EXTRAVERSION):.2f}")
    print(f"Agreeableness (updated): {model.get_trait_value(PersonalityTrait.AGREEABLENESS):.2f}")
    print(f"Dominant Emotion: {model.get_dominant_emotion()[0].value} ({model.get_dominant_emotion()[1]:.2f})")
    print(f"Secondary Emotions: {model.current_emotion.secondary_emotions}")
    print(f"Preferred Phrases: {model.get_communication_aspect(CommunicationStyleAspect.PREFERRED_PHRASES)}")
    print(f"Last updated: {time.ctime(model.last_updated_timestamp)}")

    # Test trait update logic more directly
    model.update_trait(PersonalityTrait.VERBOSITY, 0.2, 0.5) # Initial
    print(f"Initial Verbosity: {model.get_trait_value(PersonalityTrait.VERBOSITY):.3f} (Conf: {model.base_traits[PersonalityTrait.VERBOSITY].confidence:.2f})")
    model.update_trait(PersonalityTrait.VERBOSITY, 0.8, 0.9) # Strong update towards high verbosity
    print(f"Updated Verbosity: {model.get_trait_value(PersonalityTrait.VERBOSITY):.3f} (Conf: {model.base_traits[PersonalityTrait.VERBOSITY].confidence:.2f})")
    # Expected: value shifts significantly towards 0.8. Confidence also updates.
    # With adaptability 0.7, weight_new for 0.9 confidence is 0.9 * (0.5+0.7) = 0.9 * 1.2 = 1.08
    # value = (0.2*0.5*(1-1.08) + 0.8*1.08) / (0.5*(1-1.08) + 1.08)
    # value = (0.1 * -0.08 + 0.864) / (-0.04 + 1.08) = (-0.008 + 0.864) / 1.04 = 0.856 / 1.04 = ~0.823
    self.assertTrue(abs(model.get_trait_value(PersonalityTrait.VERBOSITY) - 0.823) < 0.01) # Rough check

if __name__ == "__main__":
    import time # Ensure time is imported for the main block
    def assertTrue(condition, message=""): assert condition, message # For direct run
    self = type('self', (object,), {'assertTrue': staticmethod(assertTrue)})()

    model = BehavioralModel(persona_id="doppel_jane_001", adaptability_level=0.7)
    model.update_trait(PersonalityTrait.OPENNESS, 0.7, 0.8)
    model.update_trait(PersonalityTrait.EXTRAVERSION, 0.6, 0.9)
    model.update_trait(PersonalityTrait.FORMALITY, 0.3, 0.7)
    model.update_trait(PersonalityTrait.HUMOROUSNESS, 0.8, 0.6)
    model.update_communication_aspect(CommunicationStyleAspect.TONE, "Playful-Optimistic")
    model.add_preferred_phrase("You betcha!")
    model.add_preferred_phrase("Sounds like a plan.")
    model.update_emotion(Emotion.HAPPY, 0.7)
    print(f"--- Initial Model for {model.persona_id} (v{model.version}) ---") # ... (prints) ...
    model.simulate_neuroplasticity_on_experience("positive_interaction_feedback", {})
    model.simulate_neuroplasticity_on_experience("learned_new_phrase", {"phrase": "No problemo!"})
    model.update_emotion(Emotion.CURIOUS, 0.8, secondary_emotions={Emotion.HAPPY: 0.3})
    print(f"\n--- Updated Model for {model.persona_id} (v{model.version}) ---") # ... (prints) ...
    model.update_trait(PersonalityTrait.VERBOSITY, 0.2, 0.5)
    initial_verbosity_val = model.get_trait_value(PersonalityTrait.VERBOSITY)
    model.update_trait(PersonalityTrait.VERBOSITY, 0.8, 0.9)
    updated_verbosity_val = model.get_trait_value(PersonalityTrait.VERBOSITY)
    # print(f"DEBUG: Initial V: {initial_verbosity_val}, Updated V: {updated_verbosity_val}")
    self.assertTrue(abs(updated_verbosity_val - 0.82307) < 0.001, f"Verbosity calculation mismatch. Got {updated_verbosity_val}")
    print("BehavioralModel example finished.")
