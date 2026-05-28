from abc import ABC, abstractmethod


class IToXlsxConverter(ABC):
    @abstractmethod
    async def convert(self, file_name: str, data: bytes) -> bytes: ...
