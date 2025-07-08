from typing import Dict, Any, Optional, List, Tuple

from project_doppelganger.src.ai_vcpu_core import (
    AIVCPU, TaskRequest, TaskPriority, CoreType, TaskStatus
)
from .behavioral_model import PersonalityTrait, TraitScore, CommunicationStyleAspect

class PersonalityExtractor:
    """
    Uses the AI-vCPU (e.g., Language_Modeler core) to analyze processed data
    (e.g., text, audio features) and extract personality traits, communication style, etc.
    """
    def __init__(self, vcpu: AIVCPU):
        self.vcpu = vcpu

    async def extract_traits_from_text_async(self, persona_id: str, text_content: str,
                                             data_key_prefix: str = "text_analysis") -> Dict[PersonalityTrait, TraitScore]:
        """
        Analyzes text content to extract personality traits using the AIVCPU.
        This is a conceptual implementation. The actual "analyze_text_for_traits" instruction
        would require a sophisticated model on the AI-vCPU.
        """
        if not text_content.strip():
            return {}

        task_id_traits = f"{data_key_prefix}_{persona_id}_traits_{hash(text_content)[:8]}"

        # In a real system, the AIVCPU's LanguageModeler core would have a model
        # that can infer Big Five traits, formality, etc., from text.
        # Here, we simulate this by having the task return mock trait scores.
        task_req = TaskRequest(
            task_id=task_id_traits,
            instruction="analyze_text_for_traits", # Hypothetical instruction
            data={"text": text_content, "persona_id": persona_id},
            data_key=task_id_traits, # Cache key for this analysis input/output
            priority=TaskPriority.MEDIUM,
            complexity=7, # Higher complexity for trait analysis
            required_core_type=CoreType.LANGUAGE_MODELER
        )

        # Store the input data for the task if it's not already cached by data_key
        # self.vcpu.shared_cache_hierarchy.write_hierarchical(task_req.data_key, task_req.data)
        # The AIVCPU core should handle data caching based on data_key if task_req.data is provided.

        submitted_task_id = await self.vcpu.submit_task(task_req)

        # Wait for the result
        # In a real scenario, this might be part of a larger pipeline.
        # We'll wait for a short duration for this simulation.
        task_result = await self.vcpu.get_task_result(submitted_task_id, wait_timeout_sec=5.0)

        extracted_traits: Dict[PersonalityTrait, TraitScore] = {}

        if task_result and task_result.status == TaskStatus.COMPLETED and task_result.result_data:
            # Assume result_data is a dictionary like:
            # {"traits": {"Openness": {"value": 0.7, "confidence": 0.8}, ...}}
            raw_traits_data = task_result.result_data.get("traits", {})
            for trait_name, score_data in raw_traits_data.items():
                try:
                    trait_enum = PersonalityTrait[trait_name.upper()] # Map string name to Enum
                    extracted_traits[trait_enum] = TraitScore(
                        value=float(score_data.get("value", 0.5)),
                        confidence=float(score_data.get("confidence", 0.5))
                    )
                except (KeyError, ValueError) as e:
                    print(f"Warning: Could not parse trait '{trait_name}' from AIVCPU result: {e}")
        elif task_result:
            print(f"Warning: Task {submitted_task_id} for trait extraction failed or timed out. Status: {task_result.status}, Error: {task_result.error_message}")
        else:
            print(f"Warning: Task {submitted_task_id} for trait extraction yielded no result after timeout.")

        return extracted_traits

    async def extract_communication_style_from_text_async(
            self, persona_id: str, text_content: str,
            data_key_prefix: str = "comm_style_analysis"
            ) -> Dict[CommunicationStyleAspect, Any]:
        """
        Analyzes text to extract communication style aspects. Conceptual.
        """
        if not text_content.strip():
            return {}

        task_id_style = f"{data_key_prefix}_{persona_id}_style_{hash(text_content)[:8]}"
        task_req = TaskRequest(
            task_id=task_id_style,
            instruction="analyze_text_for_communication_style", # Hypothetical
            data={"text": text_content, "persona_id": persona_id},
            data_key=task_id_style,
            priority=TaskPriority.MEDIUM,
            complexity=6,
            required_core_type=CoreType.LANGUAGE_MODELER
        )
        submitted_task_id = await self.vcpu.submit_task(task_req)
        task_result = await self.vcpu.get_task_result(submitted_task_id, wait_timeout_sec=5.0)

        extracted_style: Dict[CommunicationStyleAspect, Any] = {}
        if task_result and task_result.status == TaskStatus.COMPLETED and task_result.result_data:
            # Assume result_data: {"style": {"TONE": "neutral", "PREFERRED_PHRASES": ["phrase1"]}}
            raw_style_data = task_result.result_data.get("style", {})
            for aspect_name, value in raw_style_data.items():
                try:
                    aspect_enum = CommunicationStyleAspect[aspect_name.upper()]
                    extracted_style[aspect_enum] = value
                except KeyError:
                    print(f"Warning: Unknown communication style aspect '{aspect_name}' from AIVCPU.")
        elif task_result:
             print(f"Warning: Task {submitted_task_id} for style extraction failed. Status: {task_result.status}, Error: {task_result.error_message}")
        else:
            print(f"Warning: Task {submitted_task_id} for style extraction yielded no result.")

        return extracted_style

    # Placeholder for extracting common phrases, keywords, etc.
    async def extract_key_phrases_and_sentiment_async(
        self, persona_id: str, text_content: str,
        data_key_prefix: str = "text_entities_sentiment"
        ) -> Dict[str, Any] :
        """
        Analyzes text for key phrases/entities and overall sentiment. Conceptual.
        """
        if not text_content.strip():
            return {}

        task_id = f"{data_key_prefix}_{persona_id}_entities_{hash(text_content)[:8]}"
        task_req = TaskRequest(
            task_id=task_id,
            instruction="extract_entities_and_sentiment", # Hypothetical
            data={"text": text_content, "persona_id": persona_id},
            data_key=task_id,
            priority=TaskPriority.MEDIUM,
            complexity=5,
            required_core_type=CoreType.LANGUAGE_MODELER
        )
        submitted_task_id = await self.vcpu.submit_task(task_req)
        task_result = await self.vcpu.get_task_result(submitted_task_id, wait_timeout_sec=5.0)

        analysis_results: Dict[str, Any] = {}
        if task_result and task_result.status == TaskStatus.COMPLETED and task_result.result_data:
            # Example: {"entities": ["Paris", "Eiffel Tower"], "sentiment": {"label": "positive", "score": 0.8}}
            analysis_results = task_result.result_data
        elif task_result:
            print(f"Warning: Task {submitted_task_id} for entity/sentiment extraction failed. Status: {task_result.status}, Error: {task_result.error_message}")
        else:
            print(f"Warning: Task {submitted_task_id} for entity/sentiment extraction yielded no result.")
        return analysis_results


# Example Usage (requires a running AIVCPU and a core that can handle these instructions)
async def main():
    from project_doppelganger.src.ai_vcpu_core import AIVCPUConfig

    # --- Mocking AIVCPU and Core behavior for standalone test ---
    class MockAICore: # Simplified mock core
        def __init__(self, core_type):
            self.core_type = core_type
            self.status = "Idle"

        async def process_task(self, task_request: TaskRequest):
            # Simulate processing and return mock data based on instruction
            await asyncio.sleep(0.01) # Simulate work

            mock_result_data = {}
            if task_request.instruction == "analyze_text_for_traits":
                mock_result_data = {
                    "traits": {
                        "OPENNESS": {"value": 0.65, "confidence": 0.7},
                        "EXTRAVERSION": {"value": 0.8, "confidence": 0.75},
                        "FORMALITY": {"value": 0.3, "confidence": 0.8}
                    }
                }
            elif task_request.instruction == "analyze_text_for_communication_style":
                mock_result_data = {
                    "style": {
                        "TONE": "Enthusiastic",
                        "PREFERRED_PHRASES": ["Awesome!", "Let's do it!"]
                    }
                }
            elif task_request.instruction == "extract_entities_and_sentiment":
                 mock_result_data = {
                    "entities": ["Project Doppelganger", "AI"],
                    "sentiment": {"label": "positive", "score": 0.9}
                }

            from project_doppelganger.src.ai_vcpu_core.ai_vcpu import TaskResult, TaskStatus # Local import
            return TaskResult(
                task_id=task_request.task_id,
                request=task_request,
                status=TaskStatus.COMPLETED,
                result_data=mock_result_data,
                core_id_executed_on=0 # Mock core ID
            )

    class MockAIVCPU: # Simplified mock AIVCPU
        def __init__(self):
            self.mock_core = MockAICore(CoreType.LANGUAGE_MODELER)
            self.task_results_store = {}

        async def submit_task(self, task_request: TaskRequest) -> str:
            # Directly "process" with mock core
            print(f"MockAIVCPU: Submitting task {task_request.task_id} for instruction {task_request.instruction}")
            result = await self.mock_core.process_task(task_request)
            self.task_results_store[task_request.task_id] = result
            return task_request.task_id

        async def get_task_result(self, task_id: str, wait_timeout_sec: Optional[float] = None) -> Optional[Any]:
            # Add a small delay to simulate async behavior if waiting
            if wait_timeout_sec and wait_timeout_sec > 0:
                await asyncio.sleep(0.001)
            return self.task_results_store.get(task_id)

    # --- End Mocking ---

    mock_vcpu = MockAIVCPU()
    extractor = PersonalityExtractor(vcpu=mock_vcpu) # type: ignore

    sample_text = "This is an amazing piece of work for Project Doppelganger! I'm so excited about the future of AI. Let's do it!"
    persona_id = "test_persona_extractor"

    print("\n--- Extracting Traits ---")
    traits = await extractor.extract_traits_from_text_async(persona_id, sample_text)
    print(f"Extracted Traits: {traits}")
    if traits:
        assert PersonalityTrait.OPENNESS in traits
        assert traits[PersonalityTrait.OPENNESS].value == 0.65

    print("\n--- Extracting Communication Style ---")
    style = await extractor.extract_communication_style_from_text_async(persona_id, sample_text)
    print(f"Extracted Style: {style}")
    if style:
        assert style.get(CommunicationStyleAspect.TONE) == "Enthusiastic"
        assert "Awesome!" in style.get(CommunicationStyleAspect.PREFERRED_PHRASES, [])

    print("\n--- Extracting Key Phrases & Sentiment ---")
    analysis = await extractor.extract_key_phrases_and_sentiment_async(persona_id, sample_text)
    print(f"Extracted Analysis: {analysis}")
    if analysis:
        assert "Project Doppelganger" in analysis.get("entities", [])
        assert analysis.get("sentiment", {}).get("label") == "positive"

    print("\nPersonalityExtractor example finished.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
