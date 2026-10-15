from abc import ABC, abstractmethod


class IMarkdownRenderer[T](ABC):
    @abstractmethod
    async def render(self, document: T) -> str: ...
