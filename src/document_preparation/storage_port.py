from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


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
