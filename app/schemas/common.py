"""Base schema config and shared response shapes.

All API payloads use ``camelCase`` on the wire (see api.md) while the Python
code stays ``snake_case``. ``Money`` keeps ``Decimal`` precision internally and
serializes to a JSON number.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel

Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: float(v), return_type=float, when_used="json"),
]

T = TypeVar("T")


class CamelModel(BaseModel):
    """Base for every request/response schema."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class PageParams(CamelModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page(CamelModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        if self.page_size == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @classmethod
    def create(cls, items: list[T], total: int, params: PageParams) -> Page[T]:
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )


class Message(CamelModel):
    success: bool = True
    message: str
