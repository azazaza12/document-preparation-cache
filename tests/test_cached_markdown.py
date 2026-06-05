from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.application import DocumentNotFoundError
from app.domain.entities.single_supplier import SingleSupplierDocument
from app.domain.ports.documents import DoclingDocumentContent, MarkdownDocumentContent
from app.infrastructure.storages.minio_storage import CachedDoclingMarkdownStorage


@pytest.mark.asyncio
async def test_cached_docling_markdown_storage_returns_cached_markdown() -> None:
    markdown_storage = MagicMock()
    markdown_storage.get = AsyncMock(
        return_value=MarkdownDocumentContent(content="# cached")
    )
    markdown_storage.set = AsyncMock()

    docling_storage = MagicMock()
    docling_storage.get = AsyncMock()

    storage = CachedDoclingMarkdownStorage(markdown_storage, docling_storage)
    document = SingleSupplierDocument(id=uuid4(), file_name="doc.pdf")

    loaded = await storage.get(document)

    assert loaded.content == "# cached"
    markdown_storage.get.assert_awaited_once_with(document)
    markdown_storage.set.assert_not_awaited()
    docling_storage.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_docling_markdown_storage_builds_and_caches_on_miss() -> None:
    markdown_storage = MagicMock()
    markdown_storage.get = AsyncMock(side_effect=DocumentNotFoundError)
    markdown_storage.set = AsyncMock()

    docling_document = MagicMock()
    docling_document.model_dump.return_value = {"doc": "ling"}

    docling_storage = MagicMock()
    docling_storage.get = AsyncMock(
        return_value=DoclingDocumentContent(content=docling_document)
    )

    task_result = SimpleNamespace(return_value="# generated")
    task = MagicMock()
    task.wait_result = AsyncMock(return_value=task_result)

    storage = CachedDoclingMarkdownStorage(markdown_storage, docling_storage)
    document = SingleSupplierDocument(id=uuid4(), file_name="doc.pdf")

    with patch(
        "app.infrastructure.storages.minio_storage.docling_to_markdown.kiq",
        new=AsyncMock(return_value=task),
    ) as kiq:
        loaded = await storage.get(document)

    assert loaded.content == "# generated"
    markdown_storage.get.assert_awaited_once_with(document)
    docling_storage.get.assert_awaited_once_with(document)
    docling_document.model_dump.assert_called_once_with()
    kiq.assert_awaited_once_with(document={"doc": "ling"})
    markdown_storage.set.assert_awaited_once()

    cached_document, cached_content = markdown_storage.set.await_args.args
    assert cached_document == document
    assert cached_content.content == "# generated"


@pytest.mark.asyncio
async def test_cached_docling_markdown_storage_deletes_cached_markdown() -> None:
    markdown_storage = MagicMock()
    markdown_storage.delete = AsyncMock()
    docling_storage = MagicMock()

    storage = CachedDoclingMarkdownStorage(markdown_storage, docling_storage)
    document = SingleSupplierDocument(id=uuid4(), file_name="doc.pdf")

    await storage.delete(document)

    markdown_storage.delete.assert_awaited_once_with(document)
