from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.domain.ports.documents import PreparedDocumentContent


if TYPE_CHECKING:
    from app.domain.entities import BaseDocument


class IPreparedStrategy(ABC):
    @abstractmethod
    def supports(self, extension: str | None) -> bool: ...

    @abstractmethod
    def resolve_file_name(
        self, document: BaseDocument, extension: str | None
    ) -> str: ...

    @abstractmethod
    async def prepare(
        self, document: BaseDocument, raw: bytes, extension: str | None
    ) -> PreparedDocumentContent: ...
