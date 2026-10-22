import asyncio
from typing import Any

from pydantic import BaseModel
from pydantic_ai.messages import (
    InstructionPart,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from app.llm import ModelRole, complete

_PROFILE = ModelProfile(
    supports_tools=False,
    supports_json_schema_output=True,
    default_structured_output_mode="native",
)


class CompleteModel(Model):
    def __init__(
        self,
        role: ModelRole,
        output: type[BaseModel],
        *,
        purpose: str,
        game_id: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        super().__init__(profile=_PROFILE)
        self._role = role
        self._output = output
        self._purpose = purpose
        self._game_id = game_id
        self._max_tokens = max_tokens

    @property
    def model_name(self) -> str:
        return self._role.value

    @property
    def system(self) -> str:
        return "mendacia"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        _, params = self.prepare_request(model_settings, model_request_parameters)
        if params.output_mode != "native":
            raise TypeError(f"CompleteModel serves native output only, got {params.output_mode}")
        out = await asyncio.to_thread(
            complete,
            self._role,
            to_chat(messages, params),
            response_format=self._output,
            purpose=self._purpose,
            game_id=self._game_id,
            max_tokens=self._max_tokens,
        )
        return ModelResponse(
            parts=[TextPart(out.text)],
            model_name=out.model,
            provider_name="mendacia",
            usage=RequestUsage(input_tokens=out.prompt_tokens, output_tokens=out.completion_tokens),
        )


def to_chat(messages: list[ModelMessage], params: ModelRequestParameters) -> list[dict[str, Any]]:
    chat: list[dict[str, Any]] = []
    if params.instruction_parts:
        chat.append({"role": "system", "content": InstructionPart.join(params.instruction_parts)})
    for message in messages:
        if isinstance(message, ModelRequest):
            for req in message.parts:
                if isinstance(req, SystemPromptPart):
                    chat.append({"role": "system", "content": req.content})
                elif isinstance(req, UserPromptPart) and isinstance(req.content, str):
                    chat.append({"role": "user", "content": req.content})
                elif isinstance(req, RetryPromptPart):
                    chat.append({"role": "user", "content": req.model_response()})
                else:
                    raise TypeError(f"unsupported request part: {type(req).__name__}")
        else:
            for res in message.parts:
                if not isinstance(res, TextPart):
                    raise TypeError(f"unsupported response part: {type(res).__name__}")
                chat.append({"role": "assistant", "content": res.content})
    return chat
