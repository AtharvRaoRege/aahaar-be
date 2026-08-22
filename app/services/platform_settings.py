from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_setting import OPEN_REGISTRATION_KEY, PlatformSetting


class PlatformSettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str, default: str = "") -> str:
        row = await self.session.scalar(
            select(PlatformSetting).where(PlatformSetting.key == key)
        )
        return row.value if row is not None else default

    async def set(self, key: str, value: str, *, commit: bool = True) -> PlatformSetting:
        row = await self.session.scalar(
            select(PlatformSetting).where(PlatformSetting.key == key)
        )
        if row is None:
            row = PlatformSetting(key=key, value=value)
            self.session.add(row)
        else:
            row.value = value
        if commit:
            await self.session.commit()
            await self.session.refresh(row)
        else:
            await self.session.flush()
        return row

    async def is_open_registration(self) -> bool:
        return (await self.get(OPEN_REGISTRATION_KEY, "false")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    async def set_open_registration(self, enabled: bool) -> bool:
        await self.set(OPEN_REGISTRATION_KEY, "true" if enabled else "false")
        return enabled
