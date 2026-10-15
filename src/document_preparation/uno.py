import asyncio

from document_preparation.conversion import ConversionTarget
from document_preparation.converter_port import IFormatConverter
from document_preparation.uno_subprocess import UnoConverterSettings, unoconvert


class UnoConverter(IFormatConverter):
    def __init__(
        self, settings: UnoConverterSettings, target: ConversionTarget
    ) -> None:
        self._settings = settings
        self._target = target

    async def convert(self, file_name: str, data: bytes) -> bytes:
        return await asyncio.to_thread(
            unoconvert, self._settings, data, self._target, file_name=file_name
        )
