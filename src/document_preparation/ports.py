from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from document_preparation.content import PreparedDocumentContent


if TYPE_CHECKING:
    from document_preparation.documents import Document


class IDocumentStorage[C](ABC):
    @abstractmethod
    async def set(self, document: Document, content: C) -> None:
        pass

    @abstractmethod
    async def get(self, document: Document) -> C:
        pass

    @abstractmethod
    async def delete(self, document: Document) -> None:
        pass


class IPreparedStrategy(ABC):
    @abstractmethod
    def supports(self, extension: str | None) -> bool: ...

    @abstractmethod
    def resolve_file_name(self, document: Document, extension: str | None) -> str: ...

    @abstractmethod
    async def prepare(
        self, document: Document, raw: bytes, extension: str | None
    ) -> PreparedDocumentContent: ...


class IFormatConverter(ABC):
    @abstractmethod
    async def convert(self, file_name: str, data: bytes) -> bytes: ...


class IMarkdownRenderer[T](ABC):
    @abstractmethod
    async def render(self, document: T) -> str: ...
