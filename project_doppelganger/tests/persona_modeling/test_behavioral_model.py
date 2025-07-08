import unittest
import time
from project_doppelganger.src.persona_modeling.behavioral_model import (
    BehavioralModel,
    PersonalityTrait,
    TraitScore,
    Emotion,
    CurrentEmotionalState,
    CommunicationStyleAspect,
    CommunicationStyleProfile
)

class TestBehavioralModel(unittest.TestCase):

    def setUp(self):
        self.model = BehavioralModel(persona_id="test_persona_bm", adaptability_level=0.5)

    def test_initialization(self):
        self.assertEqual(self.model.persona_id, "test_persona_bm")
        self.assertEqual(self.model.adaptability_level, 0.5)
        self.assertIsNotNone(self.model.last_updated_timestamp)
        self.assertEqual(self.model.version, 1)
        self.assertEqual(self.model.base_traits, {})
        self.assertEqual(self.model.current_emotion.dominant_emotion, Emotion.NEUTRAL)
        self.assertEqual(self.model.communication_style.aspects, {})

    def test_update_trait_new(self):
        self.model.update_trait(PersonalityTrait.OPENNESS, 0.75, 0.9)
        self.assertIn(PersonalityTrait.OPENNESS, self.model.base_traits)
        self.assertAlmostEqual(self.model.base_traits[PersonalityTrait.OPENNESS].value, 0.75)
        self.assertAlmostEqual(self.model.base_traits[PersonalityTrait.OPENNESS].confidence, 0.9)
        self.assertEqual(self.model.version, 2)

    def test_update_trait_existing(self):
        # Initial set
        self.model.update_trait(PersonalityTrait.EXTRAVERSION, 0.6, 0.8) # v2
        initial_timestamp = self.model.last_updated_timestamp
        time.sleep(0.001) # Ensure timestamp changes

        # Update (adaptability=0.5, new_confidence=0.7, weight_new = 0.7 * (0.5+0.5) = 0.7)
        # value = (0.6*0.8*(1-0.7) + 0.9*0.7) / (0.8*(1-0.7) + 0.7)
        # value = (0.48*0.3 + 0.63) / (0.8*0.3 + 0.7)
        # value = (0.144 + 0.63) / (0.24 + 0.7) = 0.774 / 0.94 = ~0.8234
        # confidence = (0.8+0.7)/2 = 0.75
        self.model.update_trait(PersonalityTrait.EXTRAVERSION, 0.9, 0.7) # v3

        self.assertAlmostEqual(self.model.base_traits[PersonalityTrait.EXTRAVERSION].value, 0.8234, places=4)
        self.assertAlmostEqual(self.model.base_traits[PersonalityTrait.EXTRAVERSION].confidence, 0.75)
        self.assertEqual(self.model.version, 3)
        self.assertTrue(self.model.last_updated_timestamp > initial_timestamp)

    def test_update_trait_no_new_confidence(self):
        self.model.update_trait(PersonalityTrait.AGREEABLENESS, 0.5, 0.6) # v2
        # Update without new_confidence (weight_new = 0.5 * (0.5+0.5) = 0.5)
        # value = (0.5*0.6*(1-0.5) + 0.8*0.5) / (0.6*(1-0.5) + 0.5)
        # value = (0.3*0.5 + 0.4) / (0.3 + 0.5) = (0.15 + 0.4) / 0.8 = 0.55 / 0.8 = 0.6875
        # confidence = (0.6+0.5)/2 = 0.55
        self.model.update_trait(PersonalityTrait.AGREEABLENESS, 0.8) # v3
        self.assertAlmostEqual(self.model.base_traits[PersonalityTrait.AGREEABLENESS].value, 0.6875, places=4)
        self.assertAlmostEqual(self.model.base_traits[PersonalityTrait.AGREEABLENESS].confidence, 0.55)


    def test_update_emotion(self):
        self.model.update_emotion(Emotion.HAPPY, 0.8, secondary_emotions={Emotion.CURIOUS: 0.4})
        self.assertEqual(self.model.current_emotion.dominant_emotion, Emotion.HAPPY)
        self.assertAlmostEqual(self.model.current_emotion.intensity, 0.8)
        self.assertIn(Emotion.CURIOUS, self.model.current_emotion.secondary_emotions)
        self.assertAlmostEqual(self.model.current_emotion.secondary_emotions[Emotion.CURIOUS], 0.4)
        self.assertEqual(self.model.version, 2)

    def test_update_communication_aspect(self):
        self.model.update_communication_aspect(CommunicationStyleAspect.TONE, "Witty")
        self.assertEqual(self.model.communication_style.aspects[CommunicationStyleAspect.TONE], "Witty")
        self.assertEqual(self.model.version, 2)

    def test_add_preferred_phrase(self):
        self.model.add_preferred_phrase("Indeed.") # v2
        self.assertIn("Indeed.", self.model.communication_style.aspects[CommunicationStyleAspect.PREFERRED_PHRASES])

        self.model.add_preferred_phrase("Quite so.") # v3
        self.assertIn("Quite so.", self.model.communication_style.aspects[CommunicationStyleAspect.PREFERRED_PHRASES])
        self.assertEqual(len(self.model.communication_style.aspects[CommunicationStyleAspect.PREFERRED_PHRASES]), 2)

        # Adding same phrase again should not duplicate or increment version
        version_before = self.model.version
        self.model.add_preferred_phrase("Indeed.")
        self.assertEqual(len(self.model.communication_style.aspects[CommunicationStyleAspect.PREFERRED_PHRASES]), 2)
        self.assertEqual(self.model.version, version_before)


    def test_get_trait_value(self):
        self.assertIsNone(self.model.get_trait_value(PersonalityTrait.NEUROTICISM))
        self.model.update_trait(PersonalityTrait.NEUROTICISM, 0.2, 0.9)
        self.assertAlmostEqual(self.model.get_trait_value(PersonalityTrait.NEUROTICISM), 0.2)

    def test_get_dominant_emotion(self):
        self.assertEqual(self.model.get_dominant_emotion(), (Emotion.NEUTRAL, 0.5))
        self.model.update_emotion(Emotion.SAD, 0.9)
        self.assertEqual(self.model.get_dominant_emotion(), (Emotion.SAD, 0.9))

    def test_get_communication_aspect(self):
        self.assertIsNone(self.model.get_communication_aspect(CommunicationStyleAspect.LEXICAL_DIVERSITY))
        self.model.update_communication_aspect(CommunicationStyleAspect.LEXICAL_DIVERSITY, 0.85)
        self.assertAlmostEqual(self.model.get_communication_aspect(CommunicationStyleAspect.LEXICAL_DIVERSITY), 0.85)

    def test_simulate_neuroplasticity_on_experience_positive_feedback(self):
        self.model.update_trait(PersonalityTrait.AGREEABLENESS, 0.5, 0.7) # v2
        initial_agreeableness = self.model.base_traits[PersonalityTrait.AGREEABLENESS].value

        self.model.simulate_neuroplasticity_on_experience("positive_interaction_feedback", {}) # v3 (trait update) + v4 (overall sim)

        updated_agreeableness = self.model.get_trait_value(PersonalityTrait.AGREEABLENESS)
        self.assertIsNotNone(updated_agreeableness)
        # Increased by 0.05 * adaptability_level (0.5) = 0.025
        # The update_trait logic is complex, so we check if it increased.
        # (0.5*0.7*(1-0.6) + (0.5+0.025)*0.6) / (0.7*(1-0.6)+0.6)
        # = (0.35*0.4 + 0.525*0.6) / (0.28+0.6) = (0.14 + 0.315) / 0.88 = 0.455 / 0.88 = ~0.517
        self.assertAlmostEqual(updated_agreeableness, 0.51704, places=4)
        self.assertEqual(self.model.version, 4) # update_trait increments, then _increment_version in simulate


    def test_simulate_neuroplasticity_on_experience_learn_phrase(self):
        self.model.simulate_neuroplasticity_on_experience("learned_new_phrase", {"phrase": "Gotcha!"}) # v2 (add phrase) + v3 (overall sim)
        self.assertIn("Gotcha!", self.model.get_communication_aspect(CommunicationStyleAspect.PREFERRED_PHRASES))
        self.assertEqual(self.model.version, 3)

if __name__ == '__main__':
    unittest.main()
