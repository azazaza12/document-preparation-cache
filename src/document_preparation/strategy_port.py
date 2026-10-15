from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from document_preparation.content import PreparedDocumentContent


if TYPE_CHECKING:
    from document_preparation.documents import Document


class IPreparedStrategy(ABC):
    @abstractmethod
    def supports(self, extension: str | None) -> bool: ...

    @abstractmethod
    def resolve_file_name(self, document: Document, extension: str | None) -> str: ...

    @abstractmethod
    async def prepare(
        self, document: Document, raw: bytes, extension: str | None
    ) -> PreparedDocumentContent: ...
