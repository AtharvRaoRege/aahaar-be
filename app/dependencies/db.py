from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session

# ``get_db`` is the canonical name used throughout the API layer.
get_db = get_session

DBSession = Annotated[AsyncSession, Depends(get_db)]
