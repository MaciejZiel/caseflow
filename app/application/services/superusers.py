"""Superuser promotion and demotion workflows."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.domain.users.models import User


class SuperuserService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def set_superuser_status(
        self,
        *,
        email: str,
        is_superuser: bool,
    ) -> User:
        normalized_email = email.strip().lower()
        user = self.session.scalar(select(User).where(User.email == normalized_email))
        if user is None:
            raise NotFoundError("user", "User does not exist.")
        user.is_superuser = is_superuser
        self.session.commit()
        self.session.refresh(user)
        return user
