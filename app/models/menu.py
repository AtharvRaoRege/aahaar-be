from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class Category(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    restaurant: Mapped[Restaurant] = relationship(back_populates="categories")
    items: Mapped[list[MenuItem]] = relationship(
        back_populates="category", order_by="MenuItem.sort_order"
    )


class MenuItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "menu_items"
    __table_args__ = (
        CheckConstraint("base_price >= 0", name="ck_menu_items_base_price_nonneg"),
        CheckConstraint("spice_level >= 0 AND spice_level <= 3", name="ck_menu_items_spice_level"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_vegan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    spice_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    restaurant: Mapped[Restaurant] = relationship(back_populates="menu_items")
    category: Mapped[Category | None] = relationship(back_populates="items")
    variants: Mapped[list[MenuItemVariant]] = relationship(
        back_populates="menu_item",
        cascade="all, delete-orphan",
        order_by="MenuItemVariant.sort_order",
    )
    addons: Mapped[list[MenuItemAddon]] = relationship(
        back_populates="menu_item",
        cascade="all, delete-orphan",
        order_by="MenuItemAddon.sort_order",
    )


class MenuItemVariant(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "menu_item_variants"

    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price_delta: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    menu_item: Mapped[MenuItem] = relationship(back_populates="variants")


class MenuItemAddon(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "menu_item_addons"
    __table_args__ = (CheckConstraint("price >= 0", name="ck_menu_item_addons_price_nonneg"),)

    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    menu_item: Mapped[MenuItem] = relationship(back_populates="addons")
