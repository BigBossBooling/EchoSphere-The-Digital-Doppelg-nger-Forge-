import httpx # For async HTTP requests
import json
import os
from typing import Any, Dict, Optional, AsyncGenerator, List

from .llm_interface import AbstractLLMAdapter, LLMResponse
from .enrichment_engine import EnrichedPrompt

# Google Gemini API details (placeholders)
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
# Example model: "gemini-pro:generateContent" or "gemini-1.5-pro-latest:generateContent" for non-streaming
# For streaming: "gemini-pro:streamGenerateContent" or "gemini-1.5-pro-latest:streamGenerateContent"

DEFAULT_GEMINI_MODEL = "gemini-1.5-flash-latest" # A good default, adjust as needed

class GeminiAdapter(AbstractLLMAdapter):
    """
    Concrete adapter for Google Gemini LLMs.
    Handles API calls, rate limits (conceptual), basic error handling.

    NOTE: This is a conceptual implementation. It does not make live API calls
    without a valid API key and will simulate responses for demonstration.
    """
    def __init__(self, api_key: Optional[str] = None, model_name: str = DEFAULT_GEMINI_MODEL,
                 config: Optional[Dict[str, Any]] = None):
        super().__init__(api_key, config)
        self.model_name = model_name
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        # Default generation config for Gemini, can be overridden by EnrichedPrompt or instance config
        self.default_generation_config = {
            "temperature": 0.7,
            "topP": 1.0,
            "topK": 32,
            "maxOutputTokens": 1024,
            **(self.config.get("generation_config", {})) # Merge instance config
        }
        self.safety_settings = self.config.get("safety_settings", [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ])

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # Add timeout configurations, proxies, etc. as needed
            self.client = httpx.AsyncClient(timeout=httpx.Timeout(30.0)) # 30 sec timeout
        return self.client

    def _prepare_payload(self, prompt: EnrichedPrompt) -> Dict[str, Any]:
        """Prepares the payload for Gemini API based on the enriched prompt."""

        # Gemini uses a "contents" structure which is a list of turns.
        # System prompt can be a separate field or part of the first "user" turn's content.
        # For models that support system instructions directly:
        contents: List[Dict[str, Any]] = []

        # System Prompt Handling (if model supports dedicated system instruction)
        # Some Gemini models take system_instruction at the top level of payload.
        # Others expect it as the first part of the 'contents' if it's multi-turn.
        # For simplicity, we'll assume it can be part of the first user message or a dedicated field.
        # Let's assume `prompt.system_prompt` is a detailed instruction set.
        # It could be passed via `system_instruction` field if the model supports it.
        # For now, we'll prepend it to the user's first effective message if no dedicated field.

        # Gemini's format is a list of "Content" objects, each with "parts" and "role".
        # Role is "user" or "model". Conversation must be alternating.
        # Example:
        # "contents": [
        #   {"role": "user", "parts": [{"text": "System instructions... \n User: Hello"}]},
        #   {"role": "model", "parts": [{"text": "Model: Hi there!"}]},
        #   {"role": "user", "parts": [{"text": "User: How are you?"}]}
        # ]

        # Let's parse the user_prompt which contains history and current input
        # The EnrichedPrompt.user_prompt is: "{conversation_history_formatted}\nCurrent user input: {user_input_text}"

        # This is a simplified conversion. A robust one would parse history more carefully.
        # For now, the whole system_prompt + user_prompt (which contains history) goes into one user turn.
        # This is not ideal for multi-turn chat models but simpler for a generateContent style.
        # A better approach for multi-turn:
        # - Parse EnrichedPrompt.user_prompt (which has history) into alternating user/model turns.
        # - Prepend EnrichedPrompt.system_prompt to the very first user message or use system_instruction.

        # Simplified: Combine system and user prompt for now for non-chat-optimized models.
        # For chat models, the structure needs to be List[{"role": "user/model", "parts": [{"text": ...}]}]

        # Let's attempt a more multi-turn friendly structure if system_prompt is present
        if prompt.system_prompt:
            # Option 1: If the model has a specific system_instruction field (e.g. some newer Gemini versions)
            # payload["system_instruction"] = {"parts": [{"text": prompt.system_prompt}]}
            # Option 2: Prepend to the first user message or make it the first user message.
            # For now, we'll create a single user content block.
            # A more robust adapter would parse prompt.user_prompt (which has history)
            # and construct a proper alternating turn list.

            # This is a placeholder for how one might structure it for a model like Gemini 1.5 Pro
            # which can take a system instruction and then a list of contents.
            # For a simple "generateContent" with gemini-pro, it's usually just one "contents" blob.

            # Simplified for this example: Assume we are building for a model that takes a list of contents.
            # We'll put system prompt as first user message, then the actual user prompt.
            # This is NOT the ideal way for system prompts if the model has a dedicated field.

            # Let's assume a model structure that takes a single block of text for "generateContent"
            # and we combine system and user prompts.
            # For "streamGenerateContent", it's similar.

            # A more correct way for multi-turn chat models:
            # contents = []
            # if prompt.system_prompt:
            #   # This depends on whether the model expects system prompt as part of contents or a separate field
            #   # contents.append({"role": "system", "parts": [{"text": prompt.system_prompt}]}) # If "system" role is supported
            #   # Or prepend to first user message:
            #   first_user_message = f"{prompt.system_prompt}\n\n{prompt.user_prompt}"
            #   contents.append({"role": "user", "parts": [{"text": first_user_message}]})
            # else:
            #   contents.append({"role": "user", "parts": [{"text": prompt.user_prompt}]})
            # This needs to be more robust based on parsing history from prompt.user_prompt

            # For this conceptual adapter, we'll send the system prompt and user prompt combined
            # as the primary content. This is more like a completion model.
            full_text_prompt = f"{prompt.system_prompt}\n\n{prompt.user_prompt}"
            contents = [{"role": "user", "parts": [{"text": full_text_prompt}]}]

        else: # No system prompt
            contents = [{"role": "user", "parts": [{"text": prompt.user_prompt}]}]


        generation_config = self.default_generation_config.copy()
        if "temperature_modifier" in prompt.llm_config_overrides: # This is a modifier
            base_temp = generation_config.get("temperature", 0.7)
            generation_config["temperature"] = max(0.0, min(2.0, base_temp + prompt.llm_config_overrides["temperature_modifier"]))
        if "max_tokens" in prompt.llm_config_overrides:
            generation_config["maxOutputTokens"] = prompt.llm_config_overrides["max_tokens"]

        payload = {
            "contents": contents,
            "generationConfig": generation_config,
            "safetySettings": self.safety_settings
        }
        return payload

    async def generate_response(self, prompt: EnrichedPrompt) -> LLMResponse:
        if not self.api_key:
            # Simulate response if no API key
            sim_text = f"SIMULATED Gemini response to: '{prompt.user_prompt[-50:]}'. System: '{prompt.system_prompt[:50]}...'"
            return LLMResponse(text=sim_text, metadata={"simulated": True, "model": self.model_name})

        client = await self._get_client()
        endpoint = f"{GEMINI_API_BASE_URL}/{self.model_name}:generateContent?key={self.api_key}"
        payload = self._prepare_payload(prompt)

        try:
            api_response = await client.post(endpoint, json=payload)
            api_response.raise_for_status() # Raise HTTPStatusError for bad responses (4xx or 5xx)

            response_data = api_response.json()

            # Extract text from response (structure depends on Gemini version/model)
            # Typically response_data["candidates"][0]["content"]["parts"][0]["text"]
            if response_data.get("candidates") and \
               response_data["candidates"][0].get("content") and \
               response_data["candidates"][0]["content"].get("parts"):
                generated_text = response_data["candidates"][0]["content"]["parts"][0].get("text", "")
            else: # Fallback or if structure is different / or if content filtered
                if response_data.get("promptFeedback", {}).get("blockReason"):
                    reason = response_data["promptFeedback"]["blockReason"]
                    return LLMResponse(text="", error=f"Content blocked by API. Reason: {reason}", raw_response=response_data)
                generated_text = "" # Or handle as error

            # Metadata like token usage might be available (depends on API version)
            # e.g., response_data.get("usageMetadata")
            return LLMResponse(text=generated_text, raw_response=response_data, metadata={"model": self.model_name})

        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            try: # Try to parse JSON error from Gemini
                json_error = e.response.json()
                error_message = json_error.get("error", {}).get("message", error_body)
            except ValueError:
                error_message = error_body
            return LLMResponse(text="", error=f"Gemini API Error (HTTP {e.response.status_code}): {error_message}", raw_response={"status_code": e.response.status_code, "body": error_body})
        except httpx.RequestError as e: # Other request errors like network issues
            return LLMResponse(text="", error=f"Gemini request failed: {type(e).__name__} - {e}")
        except Exception as e: # Catch-all for unexpected errors
            return LLMResponse(text="", error=f"Unexpected error in Gemini adapter: {type(e).__name__} - {e}")

    async def stream_response(self, prompt: EnrichedPrompt) -> AsyncGenerator[LLMResponse, None]:
        if not self.api_key:
            # Simulate stream if no API key
            sim_text_parts = [
                "SIMULATED ", "Gemini ", "streamed ", "response ", "to: ",
                f"'{prompt.user_prompt[-50:]}'. ", f"System: '{prompt.system_prompt[:30]}...'"
            ]
            for i, part in enumerate(sim_text_parts):
                await asyncio.sleep(0.05)
                yield LLMResponse(text=part, metadata={"simulated": True, "model": self.model_name, "is_partial": True, "chunk_index": i})
            yield LLMResponse(text="", metadata={"simulated": True, "model": self.model_name, "is_partial": False, "finish_reason": "stop"}) # Final empty chunk
            return

        client = await self._get_client()
        # Add &alt=sse for Server-Sent Events for streaming
        endpoint = f"{GEMINI_API_BASE_URL}/{self.model_name}:streamGenerateContent?key={self.api_key}&alt=sse"
        payload = self._prepare_payload(prompt)

        try:
            async with client.stream("POST", endpoint, json=payload) as response:
                response.raise_for_status() # Check for initial errors before streaming

                buffer = ""
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        line_data = line[len("data: "):]
                        try:
                            chunk_json = json.loads(line_data)
                            if chunk_json.get("candidates") and \
                               chunk_json["candidates"][0].get("content") and \
                               chunk_json["candidates"][0]["content"].get("parts"):
                                text_chunk = chunk_json["candidates"][0]["content"]["parts"][0].get("text", "")
                                buffer += text_chunk

                                # Determine if it's the final chunk based on finishReason
                                finish_reason = chunk_json["candidates"][0].get("finishReason")
                                is_final = finish_reason in ["STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "OTHER"]

                                yield LLMResponse(
                                    text=text_chunk, # Yield just the delta
                                    raw_response=chunk_json,
                                    metadata={"model": self.model_name, "is_partial": not is_final, "finish_reason": finish_reason}
                                )
                                if is_final:
                                    if finish_reason == "SAFETY":
                                        # print("Warning: Gemini stream stopped due to safety settings.")
                                        # Could yield an error response here or just stop.
                                        pass
                                    return # End generation if stream is marked finished
                            elif chunk_json.get("promptFeedback", {}).get("blockReason"): # Check for early blocking
                                reason = chunk_json["promptFeedback"]["blockReason"]
                                yield LLMResponse(text="", error=f"Content stream blocked by API. Reason: {reason}", raw_response=chunk_json)
                                return


                        except json.JSONDecodeError:
                            # print(f"Warning: Could not decode JSON line from stream: {line_data}")
                            pass # Ignore non-JSON lines or malformed data for now

        except httpx.HTTPStatusError as e:
            error_body = e.response.text # Note: response might not be fully read for stream errors
            yield LLMResponse(text="", error=f"Gemini API Stream Error (HTTP {e.response.status_code}): {error_body}", raw_response={"status_code": e.response.status_code, "body": "Stream error body may be incomplete"})
        except httpx.RequestError as e:
            yield LLMResponse(text="", error=f"Gemini stream request failed: {type(e).__name__} - {e}")
        except Exception as e:
            yield LLMResponse(text="", error=f"Unexpected error in Gemini stream adapter: {type(e).__name__} - {e}")


# Example Usage for GeminiAdapter
async def main_gemini_demo():
    # To run this demo with real calls, set GEMINI_API_KEY environment variable
    # Otherwise, it will use simulated responses.
    api_key_present = bool(os.getenv("GEMINI_API_KEY"))
    print(f"--- Gemini Adapter Demo (API Key Present: {api_key_present}) ---")

    adapter = GeminiAdapter() # Will pick up API key from env if set

    # Create a dummy EnrichedPrompt
    enriched_info = EnrichedPrompt(
        system_prompt="You are DoppelBot, a friendly and slightly quirky assistant. You love talking about space.",
        user_prompt="User: Hi DoppelBot, tell me something interesting about Mars.",
        llm_config_overrides={"temperature_modifier": 0.1} # Make it slightly more deterministic
    )

    print("\n--- Generate Response (Gemini) ---")
    response = await adapter.generate_response(enriched_info)
    if response.success:
        print(f"Success! Response: {response.text}")
        # print(f"Raw: {response.raw_response}") # Can be very verbose
        print(f"Meta: {response.metadata}")
    else:
        print(f"Error: {response.error}")
        # print(f"Raw Error Response: {response.raw_response}")


    print("\n--- Stream Response (Gemini) ---")
    full_streamed_text = ""
    async for stream_chunk in adapter.stream_response(enriched_info):
        if stream_chunk.success:
            # print(f"  Stream chunk: '{stream_chunk.text}' (Partial: {stream_chunk.metadata.get('is_partial')}, Finish: {stream_chunk.metadata.get('finish_reason')})")
            full_streamed_text += stream_chunk.text
            if not stream_chunk.metadata.get('is_partial'): # Indicates end of stream for this chunk's content
                 print(f"  Stream finished (or part finished). Current full text: '{full_streamed_text.strip()}'")
                 # If finish_reason is STOP, etc., then this is the true end.
                 if stream_chunk.metadata.get('finish_reason') not in [None, "FINISH_REASON_UNSPECIFIED"]:
                     break
        else:
            print(f"  Stream error: {stream_chunk.error}")
            break
    print(f"Final assembled streamed text: '{full_streamed_text.strip()}'")

    # Close client if it was opened
    if adapter._client:
        await adapter._client.aclose()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main_gemini_demo())
