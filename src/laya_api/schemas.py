from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NonEmptyStr = Annotated[str, Field(min_length=1)]


class NoulQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["noul"]
    instructions: NonEmptyStr


class ChoiceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["choice"]
    instructions: NonEmptyStr
    criteria: dict[NonEmptyStr, NonEmptyStr] = Field(min_length=2)


class ScoreQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["score"]
    instructions: NonEmptyStr
    criteria: list[NonEmptyStr] = Field(min_length=2)


Question = Annotated[
    NoulQuestion | ChoiceQuestion | ScoreQuestion,
    Field(discriminator="type"),
]


class DecideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str | dict[str, Any] | list[Any]
    questions: dict[NonEmptyStr, Question] = Field(min_length=1)

    def native_questions(self) -> dict[str, dict[str, Any]]:
        return {
            question_id: question.model_dump(exclude_none=True)
            for question_id, question in self.questions.items()
        }
