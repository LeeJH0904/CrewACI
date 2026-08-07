from typing import Any, Dict, List, Optional

from .base_llm import BaseLLM


class GeminiLLM(BaseLLM):
    """Google Gemini API adapter with the same interface as ``OpenAILLM``."""

    def __init__(self, model_name="gemini-2.0-flash", temperature=0.0, max_tokens=1024):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = None
        self.input_tokens = 0
        self.output_tokens = 0

    def from_config(self, config: dict):
        api_key = config.get("api_key")
        if not api_key or api_key == "<YOUR_API_KEY>":
            raise ValueError("Google API key is required to initialize Gemini client.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ImportError("Gemini support requires the 'google-genai' package.") from exc
        client_kwargs = {"api_key": api_key}
        base_url = config.get("base_url")
        if base_url:
            client_kwargs["http_options"] = types.HttpOptions(base_url=base_url)
        self.client = genai.Client(**client_kwargs)
        self.model_name = config.get("model_name", self.model_name)
        self.temperature = config.get("temperature", self.temperature)
        self.max_tokens = config.get("max_tokens", self.max_tokens)
        return self

    @staticmethod
    def _split_messages(messages: List[Dict[str, str]]):
        system_parts, contents = [], []
        for message in messages:
            role = message.get("role", "user")
            content = str(message.get("content", ""))
            if role == "system":
                system_parts.append(content)
            else:
                contents.append({
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": content}],
                })
        return system_parts, contents

    def call_llm(self, messages, temperature: Optional[float] = None,
                 json_output: bool = False, option_num: Optional[int] = None,
                 is_multi_options: bool = False) -> str:
        if self.client is None:
            raise RuntimeError("GeminiLLM must be initialized with from_config() first.")
        from google.genai import types
        system_parts, contents = self._split_messages(messages)
        config_kwargs: Dict[str, Any] = {
            "temperature": self.temperature if temperature is None else temperature,
            "max_output_tokens": self.max_tokens,
        }
        if system_parts:
            config_kwargs["system_instruction"] = "\n\n".join(system_parts)
        if json_output:
            config_kwargs["response_mime_type"] = "application/json"
        generation_config = types.GenerateContentConfig(**config_kwargs)
        count = option_num if is_multi_options and option_num else 1
        responses = []
        for _ in range(count):
            response = self.client.models.generate_content(
                model=self.model_name, contents=contents, config=generation_config
            )
            self.calculate_token_usage(response)
            responses.append(response.text or "[Empty response]")
        if count > 1:
            return type("GeminiBatchResponse", (), {
                "choices": [
                    type("Choice", (), {"message": type("Message", (), {"content": text})()})()
                    for text in responses
                ]
            })()
        return responses[0]

    def calculate_token_usage(self, response):
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            self.input_tokens += getattr(usage, "prompt_token_count", 0) or 0
            self.output_tokens += getattr(usage, "candidates_token_count", 0) or 0
