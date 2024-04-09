from __future__ import annotations
from litestar.contrib.sqlalchemy.base import UUIDAuditBase, UUIDBase
from uuid import UUID
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(UUIDAuditBase):
    rules: Mapped[list[Rule]] = relationship(back_populates="user")


class Rule(UUIDBase):
    name: Mapped[str]
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"))
    user: Mapped[User] = relationship()
    filters: Mapped[list[Filter]] = relationship(back_populates="rule")


class Filter(UUIDBase):
    expression: Mapped[str]
    rule_id: Mapped[UUID] = mapped_column(ForeignKey("rule.id"))
    rule: Mapped[Rule] = relationship()
