import asyncio
from typing import Literal

from app.config import UnoConverterSettings
from app.domain.ports.format_converter import IFormatConverter
from app.infrastructure.extraction.uno_convert import unoconvert


class UnoConverter(IFormatConverter):
    def __init__(
        self, settings: UnoConverterSettings, target: Literal["docx", "xlsx"]
    ) -> None:
        self._settings = settings
        self._target = target

    async def convert(self, file_name: str, data: bytes) -> bytes:
        return await asyncio.to_thread(
            unoconvert, self._settings, data, self._target, file_name=file_name
        )
