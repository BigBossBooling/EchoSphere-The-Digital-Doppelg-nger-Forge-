from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, AsyncGenerator

from .enrichment_engine import EnrichedPrompt # Relative import

class LLMResponse:
    """
    Represents a response from an LLM.
    """
    def __init__(self, text: str, raw_response: Optional[Dict[str, Any]] = None,
                 error: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        self.text: str = text # The main generated text content
        self.raw_response: Optional[Dict[str, Any]] = raw_response # Full API response if needed
        self.error: Optional[str] = error # Error message if generation failed
        self.metadata: Dict[str, Any] = metadata if metadata else {} # E.g., finish reason, token usage

    @property
    def success(self) -> bool:
        return self.error is None

    def __str__(self) -> str:
        if self.success:
            return f"LLMResponse(text='{self.text[:50]}...', success=True)"
        return f"LLMResponse(error='{self.error}', success=False)"

class AbstractLLMAdapter(ABC):
    """
    Abstract interface for Large Language Model adapters.
    """
    def __init__(self, api_key: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        self.api_key = api_key
        self.config = config if config else {} # Model name, default temp, etc.

    @abstractmethod
    async def generate_response(self, prompt: EnrichedPrompt) -> LLMResponse:
        """
        Generates a single, complete response from the LLM based on the enriched prompt.
        """
        pass

    @abstractmethod
    async def stream_response(self, prompt: EnrichedPrompt) -> AsyncGenerator[LLMResponse, None]:
        """
        Streams responses from the LLM as they are generated (for text streaming).
        Yields LLMResponse objects, where `text` might be partial chunks.
        The final yielded response should represent the complete message or error.
        """
        # This is a placeholder for the generator structure.
        # Implementations will need to `yield` actual responses.
        # For example:
        # yield LLMResponse(text="First chunk")
        # yield LLMResponse(text="Second chunk")
        # yield LLMResponse(text="Final complete text.", metadata={"finish_reason": "stop"})
        # Or if an error occurs:
        # yield LLMResponse(error="Stream connection failed.")
        if False: # Just to make it a generator type hint wise
            yield LLMResponse(text="")


# Example of how an adapter might be configured (not part of the abstract class itself)
if __name__ == "__main__":
    # This is just for conceptual demonstration of the interface
    class DummyLLMAdapter(AbstractLLMAdapter):
        async def generate_response(self, prompt: EnrichedPrompt) -> LLMResponse:
            print(f"DummyLLMAdapter: Received system prompt: {prompt.system_prompt[:100]}...")
            print(f"DummyLLMAdapter: Received user prompt: {prompt.user_prompt[:100]}...")
            if "error" in prompt.user_prompt.lower():
                return LLMResponse(text="", error="Simulated LLM error.")

            simulated_text = f"This is a dummy response to: {prompt.user_prompt.split('Current user input:')[-1].strip()}"
            return LLMResponse(text=simulated_text, raw_response={"dummy_data": True}, metadata={"tokens_used": 10})

        async def stream_response(self, prompt: EnrichedPrompt) -> AsyncGenerator[LLMResponse, None]:
            print(f"DummyLLMAdapter: Streaming for system prompt: {prompt.system_prompt[:100]}...")
            print(f"DummyLLMAdapter: Streaming for user prompt: {prompt.user_prompt[:100]}...")

            if "error_stream" in prompt.user_prompt.lower():
                yield LLMResponse(text="", error="Simulated stream error.")
                return

            base_response_text = f"Streamed dummy response to: {prompt.user_prompt.split('Current user input:')[-1].strip()}"
            words = base_response_text.split()
            for i, word in enumerate(words):
                await asyncio.sleep(0.05) # Simulate network latency
                is_final_chunk = (i == len(words) - 1)
                yield LLMResponse(
                    text=word + " ",
                    metadata={"is_partial": not is_final_chunk,
                              "chunk_index": i,
                              "finish_reason": "stop" if is_final_chunk else None}
                )
            # The final response in a stream could consolidate the text, or the consumer does.
            # Here, we assume consumer concatenates. The last yielded item can carry final metadata.

    async def demo():
        adapter = DummyLLMAdapter()

        # Create a dummy EnrichedPrompt
        enriched_info = EnrichedPrompt(
            system_prompt="You are a helpful assistant.",
            user_prompt="User: Tell me a joke.",
            llm_config_overrides={"temperature": 0.7}
        )

        print("--- Generate Response Demo ---")
        response = await adapter.generate_response(enriched_info)
        if response.success:
            print(f"Success! Response: {response.text}")
            print(f"Raw: {response.raw_response}, Meta: {response.metadata}")
        else:
            print(f"Error: {response.error}")

        print("\n--- Stream Response Demo ---")
        full_streamed_text = ""
        async for stream_chunk in adapter.stream_response(enriched_info):
            if stream_chunk.success:
                print(f"  Stream chunk: '{stream_chunk.text}' (Partial: {stream_chunk.metadata.get('is_partial')})")
                full_streamed_text += stream_chunk.text
                if not stream_chunk.metadata.get('is_partial'):
                    print(f"  Stream finished. Full text: '{full_streamed_text.strip()}'")
            else:
                print(f"  Stream error: {stream_chunk.error}")
                break

        print("\n--- Error Simulation Demo ---")
        error_prompt = EnrichedPrompt(system_prompt="You are helpful.", user_prompt="User: please cause an error.")
        error_response = await adapter.generate_response(error_prompt)
        print(f"Error response: Success={error_response.success}, Error='{error_response.error}'")


    if __name__ == "__main__":
        import asyncio
        asyncio.run(demo())
