import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Dict, Any
import asyncio

# Adjust import path for tests
try:
    from maipp.ai_adapters.base_adapter import BaseAIAdapter, AIAdapterError
    from maipp.ai_adapters.google_gemini_adapter import GoogleGeminiAdapter
    from maipp.config import Settings # Assuming settings are used by adapters for API keys
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from maipp.ai_adapters.base_adapter import BaseAIAdapter, AIAdapterError
    from maipp.ai_adapters.google_gemini_adapter import GoogleGeminiAdapter
    from maipp.config import Settings


@pytest.fixture
def mock_gemini_settings(monkeypatch):
    settings_obj = Settings(GOOGLE_GEMINI_API_KEY="test_gemini_api_key_from_fixture")
    monkeypatch.setattr("maipp.ai_adapters.google_gemini_adapter.settings", settings_obj)
    return settings_obj

@pytest.fixture
def mock_gemini_settings_no_key(monkeypatch):
    settings_obj = Settings(GOOGLE_GEMINI_API_KEY=None) # Ensure it's None
    monkeypatch.setattr("maipp.ai_adapters.google_gemini_adapter.settings", settings_obj)
    return settings_obj

# --- Tests for BaseAIAdapter ---
class ConcreteTestAdapter(BaseAIAdapter):
    async def _initialize_client(self):
        self.client = MagicMock()
    async def analyze_text(self, text_content: str, analysis_prompt_template: str, **kwargs) -> Dict[str, Any]:
        # Simulate hashing if base class uses it, or just return mock
        prompt = analysis_prompt_template.format(text=text_content)
        return {"analysis": "mocked", "prompt_hash": self._hash_prompt(prompt)}

def test_base_adapter_instantiation_and_get_model_identifier():
    adapter = ConcreteTestAdapter(model_name="test_model_base")
    assert adapter.model_name == "test_model_base"
    assert adapter.get_model_identifier() == "ConcreteTestAdapter_test_model_base"

@pytest.mark.asyncio
async def test_base_adapter_hash_prompt():
    adapter = ConcreteTestAdapter(model_name="test_model_hash")
    await adapter._initialize_client() # Though not strictly needed for _hash_prompt
    prompt_text = "This is a test prompt."
    hashed = adapter._hash_prompt(prompt_text)
    assert isinstance(hashed, str)
    assert len(hashed) == 64 # SHA256 hash length

# --- Tests for GoogleGeminiAdapter ---
@pytest.mark.asyncio
async def test_google_gemini_adapter_initialize_client_success(mock_gemini_settings, monkeypatch):
    mock_genai_configure = MagicMock()
    mock_generative_model_instance = MagicMock()

    monkeypatch.setattr("maipp.ai_adapters.google_gemini_adapter.genai.configure", mock_genai_configure)
    monkeypatch.setattr("maipp.ai_adapters.google_gemini_adapter.genai.GenerativeModel", MagicMock(return_value=mock_generative_model_instance))

    # Adapter __init__ calls _initialize_client via asyncio.create_task
    # We need to ensure this task completes or call _initialize_client directly for predictable testing
    adapter = GoogleGeminiAdapter(model_name="gemini-test-model")
    await adapter._initialize_client() # Explicitly await for test predictability

    mock_genai_configure.assert_called_once_with(api_key=mock_gemini_settings.GOOGLE_GEMINI_API_KEY)
    adapter.genai.GenerativeModel.assert_called_once_with(adapter.model_name)
    assert adapter.client == mock_generative_model_instance

@pytest.mark.asyncio
async def test_google_gemini_adapter_initialize_client_no_api_key(mock_gemini_settings_no_key, monkeypatch):
    mock_genai_configure = MagicMock()
    monkeypatch.setattr("maipp.ai_adapters.google_gemini_adapter.genai.configure", mock_genai_configure)

    adapter = GoogleGeminiAdapter(model_name="gemini-test-model-no-key")
    await adapter._initialize_client() # Explicitly await

    assert adapter.client is None
    mock_genai_configure.assert_not_called()

@pytest.mark.asyncio
async def test_google_gemini_adapter_analyze_text_success(mock_gemini_settings, monkeypatch):
    mock_generative_model_instance = MagicMock()

    mock_candidate = MagicMock()
    mock_candidate.finish_reason.name = "STOP"
    mock_candidate.content.parts = [MagicMock(text="Topics: AI, Ethics")]
    mock_candidate.safety_ratings = []

    mock_gemini_response = MagicMock()
    mock_gemini_response.candidates = [mock_candidate]
    mock_gemini_response.prompt_feedback.block_reason = None
    mock_gemini_response.usage_metadata = MagicMock()
    mock_gemini_response.usage_metadata.to_dict.return_value = {"prompt_token_count": 10, "candidates_token_count": 3}

    adapter = GoogleGeminiAdapter(model_name="gemini-pro-test-analyze")
    adapter.client = mock_generative_model_instance # Pre-set the client

    # Mock the executor call
    async def mock_run_in_executor(executor, func, *args, **kwargs):
        return func(*args, **kwargs) # Directly call the mocked func

    monkeypatch.setattr("asyncio.get_running_loop().run_in_executor", AsyncMock(side_effect=mock_run_in_executor))
    mock_generative_model_instance.generate_content = MagicMock(return_value=mock_gemini_response)

    text_content = "About AI Ethics."
    prompt_template = "Topics: {text}"

    result = await adapter.analyze_text(text_content, prompt_template, temperature=0.1)

    assert result["model_output_text"] == "Topics: AI, Ethics"
    assert result["model_name_used"] == "gemini-pro-test-analyze"
    assert result["parameters_used"]["temperature"] == 0.1
    assert result["finish_reason"] == "STOP"

    expected_prompt = prompt_template.format(text=text_content)
    adapter.client.generate_content.assert_called_once()
    call_args_list = adapter.client.generate_content.call_args_list
    assert call_args_list[0][0][0] == expected_prompt # First arg to generate_content
    assert call_args_list[0][1]['generation_config'].temperature == 0.1 # Check kwargs

@pytest.mark.asyncio
async def test_google_gemini_adapter_analyze_text_client_not_initialized(mock_gemini_settings_no_key):
    adapter = GoogleGeminiAdapter(model_name="gemini-pro-no-client")
    await adapter._initialize_client() # Ensure client is None

    with pytest.raises(AIAdapterError, match="Google Gemini client not initialized"):
        await adapter.analyze_text("test", "test: {text}")

@pytest.mark.asyncio
async def test_google_gemini_adapter_analyze_text_api_error_safety_block(mock_gemini_settings, monkeypatch):
    adapter = GoogleGeminiAdapter(model_name="gemini-pro-safety-block")
    mock_model_instance = MagicMock()
    adapter.client = mock_model_instance

    mock_response_blocked = MagicMock()
    mock_response_blocked.candidates = [] # Or None, depending on SDK version for this case
    mock_response_blocked.prompt_feedback.block_reason = "SAFETY" # Example block reason
    mock_response_blocked.prompt_feedback.block_reason.name = "SAFETY" # Ensure .name attribute exists

    async def mock_run_in_executor_safety(executor, func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr("asyncio.get_running_loop().run_in_executor", AsyncMock(side_effect=mock_run_in_executor_safety))
    mock_model_instance.generate_content = MagicMock(return_value=mock_response_blocked)

    with pytest.raises(AIAdapterError, match="Gemini prompt blocked: SAFETY"):
        await adapter.analyze_text("some potentially problematic content", "Analyze: {text}")

@pytest.mark.asyncio
async def test_google_gemini_adapter_analyze_text_api_error_sdk_exception(mock_gemini_settings, monkeypatch):
    adapter = GoogleGeminiAdapter(model_name="gemini-pro-sdk-error")
    mock_model_instance = MagicMock()
    adapter.client = mock_model_instance

    # Simulate an exception from the SDK call itself
    from google.api_core import exceptions as google_exceptions
    sdk_error = google_exceptions.InvalidArgument("Invalid request")

    async def mock_run_in_executor_sdk_error(executor, func, *args, **kwargs):
        # Make the mocked generate_content raise the SDK error
        func.side_effect = sdk_error
        return await func(*args, **kwargs) # This will now raise

    # We need to ensure that the generate_content method itself is an AsyncMock if run_in_executor calls it with await
    # Or, more simply, make generate_content a MagicMock that *raises* the error when called by run_in_executor.
    mock_model_instance.generate_content = MagicMock(side_effect=sdk_error)
    monkeypatch.setattr("asyncio.get_running_loop().run_in_executor", AsyncMock(side_effect=lambda exec, func, *a, **kw: func(*a, **kw)))


    with pytest.raises(AIAdapterError, match="Gemini analysis failed: Invalid request"):
        await adapter.analyze_text("test content", "Prompt: {text}")

```
