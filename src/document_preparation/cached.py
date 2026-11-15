from typing import TYPE_CHECKING, override

import filetype

from document_preparation.content import (
    BinaryDocumentContent,
    MarkdownDocumentContent,
    PreparedDocumentContent,
    RenderableDocumentContent,
)
from document_preparation.exceptions import DocumentNotFoundError
from document_preparation.ports import (
    IDocumentStorage,
    IMarkdownRenderer,
    IPreparedStrategy,
)


if TYPE_CHECKING:
    from document_preparation.documents import Document


def _guess_extension(data: bytes) -> str | None:
    kind = filetype.guess(data)
    return f".{kind.extension}" if kind else None


class CachedMarkdownStorage[T](IDocumentStorage[MarkdownDocumentContent]):
    def __init__(
        self,
        markdown_storage: IDocumentStorage[MarkdownDocumentContent],
        source_storage: IDocumentStorage[RenderableDocumentContent[T]],
        renderer: IMarkdownRenderer[T],
    ) -> None:
        self._markdown_storage = markdown_storage
        self._source_storage = source_storage
        self._renderer = renderer

    @override
    async def set(self, document: Document, content: MarkdownDocumentContent) -> None:
        await self._markdown_storage.set(document, content)

    @override
    async def get(self, document: Document) -> MarkdownDocumentContent:
        try:
            return await self._markdown_storage.get(document)
        except DocumentNotFoundError:
            source = await self._source_storage.get(document)
            markdown = await self._renderer.render(source.content)
            content = MarkdownDocumentContent(content=markdown)
            await self._markdown_storage.set(document, content)
            return content

    @override
    async def delete(self, document: Document) -> None:
        await self._markdown_storage.delete(document)


class CachedPreparedDocumentStorage(IDocumentStorage[PreparedDocumentContent]):
    def __init__(
        self,
        prepared_storage: IDocumentStorage[BinaryDocumentContent],
        raw_storage: IDocumentStorage[BinaryDocumentContent],
        strategy: IPreparedStrategy,
    ) -> None:
        self._prepared_storage = prepared_storage
        self._raw_storage = raw_storage
        self._strategy = strategy

    @override
    async def set(self, document: Document, content: PreparedDocumentContent) -> None:
        await self._prepared_storage.set(
            document=document,
            content=BinaryDocumentContent(content=content.content),
        )

    @override
    async def get(self, document: Document) -> PreparedDocumentContent:
        try:
            cached = await self._prepared_storage.get(document)
        except DocumentNotFoundError:
            raw = await self._raw_storage.get(document)
            extension = _guess_extension(raw.content)
            prepared = await self._strategy.prepare(document, raw.content, extension)
            await self._prepared_storage.set(
                document=document,
                content=BinaryDocumentContent(content=prepared.content),
            )
            return prepared
        extension = _guess_extension(cached.content)
        return PreparedDocumentContent(
            content=cached.content,
            file_name=self._strategy.resolve_file_name(document, extension),
        )

    @override
    async def delete(self, document: Document) -> None:
        await self._prepared_storage.delete(document)
