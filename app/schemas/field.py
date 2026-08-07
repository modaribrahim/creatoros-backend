from pydantic import BaseModel


class FieldOut(BaseModel):
    id: str
    name: str
    type: str
    enabled: bool
    options: list[str] = []


class FieldUpdate(BaseModel):
    id: str
    name: str | None = None
    type: str | None = None
    enabled: bool | None = None
    options: list[str] | None = None
