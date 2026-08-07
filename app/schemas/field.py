from pydantic import BaseModel, Field


class FieldOut(BaseModel):
    id: str
    name: str
    type: str
    enabled: bool
    options: list[str] = []
    builtin: bool = False


class FieldCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    type: str = Field(pattern=r"^(enum|int|float|bool|string|string_list)$")
    enabled: bool = True
    options: list[str] = Field(default_factory=list, max_length=100)


class FieldUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    type: str | None = Field(
        default=None, pattern=r"^(enum|int|float|bool|string|string_list)$"
    )
    enabled: bool | None = None
    options: list[str] | None = Field(default=None, max_length=100)
