from typing import AsyncIterator
from .base import BaseLLMProvider, LLMResponse, StreamChunk
from app.config import settings


class GeminiProvider(BaseLLMProvider):
    provider_name = "gemini"

    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        self._genai = genai

    def _build_history(self, messages: list[dict]) -> tuple[list[dict], str]:
        """Convert OpenAI-style messages to Gemini history + last user message."""
        history = []
        last_user = ""
        for m in messages:
            role = m["role"]
            if role == "system":
                continue  # prepend to first user message instead
            gemini_role = "user" if role == "user" else "model"
            history.append({"role": gemini_role, "parts": [m["content"]]})
        # Pop the last user message to send as new input
        if history and history[-1]["role"] == "user":
            last_user = history[-1]["parts"][0]
            history = history[:-1]
        return history, last_user

    async def chat(self, messages: list[dict], model: str = "gemini-2.0-flash", max_tokens: int = 2048, temperature: float = 0.7) -> LLMResponse:
        import asyncio
        history, last_user = self._build_history(messages)
        gen_model = self._genai.GenerativeModel(model)
        chat_session = gen_model.start_chat(history=history)
        # Gemini SDK is sync; run in thread pool
        response = await asyncio.get_event_loop().run_in_executor(
            None, chat_session.send_message, last_user
        )
        usage = response.usage_metadata
        return LLMResponse(
            content=response.text,
            prompt_tokens=usage.prompt_token_count if usage else 0,
            completion_tokens=usage.candidates_token_count if usage else 0,
            total_tokens=usage.total_token_count if usage else 0,
            model=model,
            provider=self.provider_name,
            request_id=None,
            raw_response={},
        )

    async def stream_chat(self, messages: list[dict], model: str = "gemini-2.0-flash", max_tokens: int = 2048, temperature: float = 0.7) -> AsyncIterator[StreamChunk]:
        import asyncio
        history, last_user = self._build_history(messages)
        gen_model = self._genai.GenerativeModel(model)
        chat_session = gen_model.start_chat(history=history)

        response = await asyncio.get_event_loop().run_in_executor(
            None, lambda: chat_session.send_message(last_user, stream=True)
        )
        for chunk in response:
            if chunk.text:
                yield StreamChunk(delta=chunk.text, is_final=False)

        usage = response.usage_metadata
        yield StreamChunk(
            delta="",
            is_final=True,
            prompt_tokens=usage.prompt_token_count if usage else 0,
            completion_tokens=usage.candidates_token_count if usage else 0,
            total_tokens=usage.total_token_count if usage else 0,
        )
