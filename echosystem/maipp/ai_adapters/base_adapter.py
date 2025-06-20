# echosystem/maipp/ai_adapters/base_adapter.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
import hashlib # For hashing prompts if needed

logger = logging.getLogger(__name__)

class AIAdapterError(Exception):
    """Custom exception for AI adapter related errors."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None, status_code: Optional[int] = None, model_name: Optional[str] = None):
        super().__init__(message)
        self.original_exception = original_exception
        self.status_code = status_code # For HTTP related errors from AI services
        self.model_name = model_name
        self.message = message

    def __str__(self):
        return f"AIAdapterError (Model: {self.model_name}, Status: {self.status_code}): {self.message} (Original: {self.original_exception})"


class BaseAIAdapter(ABC):
    def __init__(self, model_name: str, api_key: Optional[str] = None, **kwargs):
        self.model_name = model_name
        self.api_key = api_key # Store API key if provided, subclasses decide how to use it
        self.init_kwargs = kwargs # For any other specific init params for the adapter
        self.client = None # To be initialized by subclasses in _initialize_client
        # Subclasses should call self._initialize_client() in their __init__

    @abstractmethod
    async def _initialize_client(self):
        """
        Initialize the specific AI service client (e.g., OpenAI, Gemini).
        This method should set self.client.
        It's called by the subclass's __init__ method.
        """
        pass

    @abstractmethod
    async def analyze_text(self, text_content: str, analysis_prompt_template: str, **kwargs) -> Dict[str, Any]:
        """
        Analyzes text content using a specific prompt or task.

        Args:
            text_content: The text to be analyzed.
            analysis_prompt_template: A string template for the prompt, e.g., "Summarize: {text}"
                                      or a more complex structure if needed by the model.
            **kwargs: Additional model-specific parameters like temperature, max_tokens, etc.

        Returns:
            A dictionary structured for RawAnalysisFeatures.extractedFeatures.
            This dictionary should be standardized by the adapter.

        Raises:
            AIAdapterError: If analysis fails.
        """
        pass

    def get_model_identifier(self) -> str:
        """
        Returns a string that identifies this adapter and model configuration.
        Useful for logging and storing in RawAnalysisFeatures.modelNameOrType.
        """
        # Using class name and model_name provides a clear identifier
        return f"{self.__class__.__name__}_{self.model_name}"

    def _hash_prompt(self, prompt: str) -> str:
        """Helper to create a SHA256 hash of the prompt for metadata/logging if needed."""
        return hashlib.sha256(prompt.encode('utf-8')).hexdigest()
