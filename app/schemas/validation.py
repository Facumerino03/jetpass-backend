from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.validation_criterion import CriterionOperator, CriterionResult


class ValidationCriterionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    field_path: str = Field(min_length=1, max_length=200)
    operator: CriterionOperator
    expected_value: str | None = None
    result_on_pass: CriterionResult
    result_on_fail: CriterionResult
    pass_message: str | None = None
    fail_message: str | None = None


class ValidationCriterionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    field_path: str | None = Field(default=None, min_length=1, max_length=200)
    operator: CriterionOperator | None = None
    expected_value: str | None = None
    result_on_pass: CriterionResult | None = None
    result_on_fail: CriterionResult | None = None
    pass_message: str | None = None
    fail_message: str | None = None


class ValidationCriterionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by_user_id: UUID
    name: str
    field_path: str
    operator: CriterionOperator
    expected_value: str | None
    result_on_pass: CriterionResult
    result_on_fail: CriterionResult
    pass_message: str | None
    fail_message: str | None
    is_active: bool


class ValidationRunRequest(BaseModel):
    flight_plan_id: UUID
    criterion_ids: list[UUID] | None = None
    block_id: UUID | None = None


class ValidationCriterionResultItem(BaseModel):
    criterion_id: UUID
    criterion_name: str
    field_path: str
    operator: CriterionOperator
    expected_value: str | None
    actual_value: str | None
    passed: bool
    result_applied: CriterionResult
    message: str | None


class ValidationRunResponse(BaseModel):
    overall: CriterionResult
    results: list[ValidationCriterionResultItem]


class ValidationBlockCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    criterion_ids: list[UUID] = Field(min_length=1)


class ValidationBlockUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    criterion_ids: list[UUID] | None = None


class ValidationBlockPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by_user_id: UUID
    name: str
    is_active: bool
    criteria: list[ValidationCriterionPublic] = Field(default_factory=list)
    criteria_count: int = 0

