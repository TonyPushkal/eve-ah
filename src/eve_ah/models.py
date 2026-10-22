"""Public chat contracts and source records."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=4000)
    history: list[Turn] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def limit_history(self):
        if sum(len(t.content) for t in self.history) > 20000:
            raise ValueError("History exceeds 20000 characters; clear the conversation.")
        return self


class Source(BaseModel):
    id: str
    name: str
    text: str
    page: int | None = None
    score: float = 0.0


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list)
    grounding: Literal["documents", "general", "insufficient"]


class EveError(Exception):
    def __init__(self, message: str, status: int = 503, code: str = "unavailable"):
        self.message = message
        self.status = status
        self.code = code
        super().__init__(message)
