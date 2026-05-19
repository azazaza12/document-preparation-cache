from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from app.domain.entities import BaseDocument


class IDocumentStorage[C](ABC):
    @abstractmethod
    async def set(self, document: BaseDocument, content: C) -> None:
        pass

    @abstractmethod
    async def get(self, document: BaseDocument) -> C:
        pass

    @abstractmethod
    async def delete(self, document: BaseDocument) -> None:
        pass
