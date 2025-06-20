# echosystem/maipp/ai_adapters/google_gemini_adapter.py
import logging
import google.generativeai as genai
from typing import Dict, Any, Optional
import asyncio # For running blocking calls in thread pool if needed

from .base_adapter import BaseAIAdapter, AIAdapterError
# Assuming config.py is in the parent directory of ai_adapters
# Adjust if your project structure requires a different import path for settings
from ..config import settings # MAIPP's config for API key

logger = logging.getLogger(__name__)

class GoogleGeminiAdapter(BaseAIAdapter):
    def __init__(self, model_name: str = "gemini-1.0-pro-latest", **kwargs): # Updated to a common model
        # Gemini API key is typically configured globally via genai.configure(api_key=...)
        # or via the GOOGLE_API_KEY environment variable.
        # We pass settings.GOOGLE_GEMINI_API_KEY to ensure it's explicitly used if set.
        super().__init__(model_name=model_name, api_key=settings.GOOGLE_GEMINI_API_KEY, **kwargs)
        # _initialize_client is now called by the superclass __init__ conceptually,
        # but practically, subclasses must call it after super().__init__() if they need self.api_key
        # For this structure, let's call it explicitly here.
        # In a real scenario, BaseAIAdapter might have a template method pattern for initialization.
        asyncio.create_task(self._initialize_client()) # Initialize client asynchronously if it involves async ops
                                            # Or make _initialize_client synchronous if genai.configure is blocking.
                                            # For genai, configure is synchronous.

    async def _initialize_client(self): # genai.configure is synchronous
        if not self.api_key:
            logger.warning("Google Gemini API key is not configured in MAIPP settings. Adapter will not function.")
            self.client = None
            return
        try:
            genai.configure(api_key=self.api_key)
            # Model name might include 'models/' prefix or not, SDK handles some variations.
            # Using the direct model name usually works.
            self.client = genai.GenerativeModel(self.model_name)
            logger.info(f"Google Gemini client initialized for model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Google Gemini client (model: {self.model_name}): {e}", exc_info=True)
            self.client = None # Ensure client is None if init fails

    async def analyze_text(self, text_content: str, analysis_prompt_template: str, **kwargs) -> Dict[str, Any]:
        if not self.client:
            raise AIAdapterError("Google Gemini client not initialized. API key might be missing, invalid, or initialization failed.", model_name=self.model_name)

        prompt = analysis_prompt_template.format(text=text_content)

        temperature = kwargs.get("temperature", 0.5) # Adjusted default for more deterministic output initially
        max_output_tokens = kwargs.get("max_output_tokens", 1024) # Increased default
        top_p = kwargs.get("top_p", None) # Optional
        top_k = kwargs.get("top_k", None) # Optional

        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            top_p=top_p,
            top_k=top_k
        )

        logger.debug(f"Sending prompt to Gemini model {self.model_name}. Prompt snippet: {prompt[:150]}...")
        try:
            # The google-generativeai SDK's generate_content is blocking.
            # To use it in an async function, it must be run in a thread pool executor.
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, # Uses default ThreadPoolExecutor
                self.client.generate_content,
                prompt,
                generation_config=generation_config
            )

            # Validate response and handle potential errors/blocks
            if not response.candidates: # Should always have candidates if no error
                logger.error(f"Gemini generation returned no candidates for prompt: {prompt[:100]}...")
                # Check for prompt feedback which might indicate blocking
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    block_reason_name = response.prompt_feedback.block_reason.name
                    logger.error(f"Gemini prompt blocked for safety reasons. Reason: {block_reason_name}")
                    raise AIAdapterError(f"Gemini prompt blocked: {block_reason_name}", status_code=400, model_name=self.model_name) # 400 for bad input due to safety
                raise AIAdapterError("Gemini generation returned no candidates without explicit blocking reason.", status_code=500, model_name=self.model_name)

            candidate = response.candidates[0]
            finish_reason_name = candidate.finish_reason.name

            if finish_reason_name not in ["STOP", "MAX_TOKENS"]:
                logger.error(f"Gemini generation finished with unexpected reason: {finish_reason_name} for prompt: {prompt[:100]}...")
                # Check safety ratings on the candidate itself
                if candidate.safety_ratings:
                    for rating in candidate.safety_ratings:
                        if rating.probability.name not in ["NEGLIGIBLE", "LOW"]: # Check for harmful categories
                             logger.error(f"Gemini content safety rating issue: Category {rating.category.name}, Probability {rating.probability.name}")
                             # Depending on policy, might raise an error here
                raise AIAdapterError(f"Gemini generation failed or finished unexpectedly: {finish_reason_name}", status_code=500, model_name=self.model_name)

            response_text = "".join(part.text for part in candidate.content.parts) # Ensure all parts are joined

            return {
                "model_output_text": response_text,
                "prompt_hash": self._hash_prompt(prompt), # Using helper from base class
                "model_name_used": self.model_name, # From adapter instance
                "parameters_used": {"temperature": temperature, "max_output_tokens": max_output_tokens, "top_p": top_p, "top_k": top_k},
                "finish_reason": finish_reason_name,
                "usage_metadata": response.usage_metadata.to_dict() if hasattr(response, 'usage_metadata') else None
            }
        except Exception as e:
            logger.error(f"Error calling Google Gemini API ({self.model_name}): {type(e).__name__} - {e}", exc_info=True)
            # Check if it's a known Google API exception type for more specific status codes
            # from google.api_core import exceptions as google_exceptions
            # if isinstance(e, google_exceptions.GoogleAPIError):
            #    status_code = e.code if hasattr(e, 'code') else 503 # Service Unavailable or specific error
            #    raise AIAdapterError(f"Gemini API error: {str(e)}", original_exception=e, status_code=status_code, model_name=self.model_name)
            raise AIAdapterError(f"Gemini analysis failed: {str(e)}", original_exception=e, model_name=self.model_name)
