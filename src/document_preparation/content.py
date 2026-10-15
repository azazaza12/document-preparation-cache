from abc import ABC
from dataclasses import dataclass


@dataclass(kw_only=True)
class BaseDocumentContent[T](ABC):
    content: T
    file_name: str | None = None


class BinaryDocumentContent(BaseDocumentContent[bytes]):
    pass


class MarkdownDocumentContent(BaseDocumentContent[str]):
    pass


class RenderableDocumentContent[T](BaseDocumentContent[T]):
    pass


@dataclass(kw_only=True)
class PreparedDocumentContent(BaseDocumentContent[bytes]):
    file_name: str
