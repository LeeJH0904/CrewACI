"""Runtime-checked result types for the CrewAI-style Sequential MAS."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ConversationEntry(ContractModel):
    turn: int = Field(ge=0)
    sender: Literal["user", "solver", "reviewer", "finalizer"]
    receiver: Literal["solver", "reviewer", "finalizer", "user"]
    phase: Literal["task", "context", "review", "final"]
    content: str


class SequentialSuccessResult(ContractModel):
    raw_response: str
    response: str
    response_agent: Literal["finalizer"]
    conversation: list[ConversationEntry]
    status: Literal["success"]

    @model_validator(mode="after")
    def check_conversation(self):
        expected = [
            (0, "user", "solver", "task"),
            (1, "solver", "reviewer", "context"),
            (2, "reviewer", "finalizer", "review"),
            (3, "finalizer", "user", "final"),
        ]
        actual = [
            (entry.turn, entry.sender, entry.receiver, entry.phase)
            for entry in self.conversation
        ]
        if actual != expected:
            raise ValueError("Sequential conversation routes or order differ")
        if self.conversation[-1].content != self.raw_response:
            raise ValueError("Final conversation content must equal raw_response")
        return self
