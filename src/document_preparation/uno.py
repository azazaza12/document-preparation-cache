import asyncio
from typing import Literal

from app.config import UnoConverterSettings
from app.domain.ports.docx_converter import IToDocxConverter
from app.infrastructure.extraction.uno_convert import unoconvert


class UnoToDocxConverter(IToDocxConverter):
    def __init__(self, settings: UnoConverterSettings) -> None:
        self.settings = settings

    async def convert(self, file_name: str, data: bytes) -> bytes:
        target: Literal["docx", "xlsx"] = "docx"
        return await asyncio.to_thread(
            unoconvert, self.settings, data, target, file_name=file_name
        )
