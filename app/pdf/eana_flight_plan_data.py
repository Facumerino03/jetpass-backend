from pydantic import BaseModel, Field, field_validator


class EanaFlightPlanPdfData(BaseModel):
    """Pure input for the EANA PDF generator. No DB or storage dependencies."""

    text_fields: dict[str, str] = Field(default_factory=dict)
    mark_fields: dict[str, bool] = Field(default_factory=dict)
    signature_png_bytes: bytes | None = None

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("text_fields")
    @classmethod
    def uppercase_text_fields(cls, value: dict[str, str]) -> dict[str, str]:
        return {key: text.upper() for key, text in value.items()}
