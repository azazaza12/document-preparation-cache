from abc import ABC
from dataclasses import dataclass

from docling_core.types.doc.document import DoclingDocument


@dataclass(kw_only=True)
class BaseDocumentContent[T](ABC):
    content: T
    file_name: str | None = None


class BinaryDocumentContent(BaseDocumentContent[bytes]):
    pass


class DoclingDocumentContent(BaseDocumentContent[DoclingDocument]):
    pass


class MarkdownDocumentContent(BaseDocumentContent[str]):
    pass


class PreparedDocumentContent(BaseDocumentContent[bytes]):
    pass
