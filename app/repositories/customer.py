from __future__ import annotations

from app.models.customer_session import CustomerSession
from app.repositories.base import BaseRepository


class CustomerSessionRepository(BaseRepository[CustomerSession]):
    model = CustomerSession
