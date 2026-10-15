from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from tests.conftest import FakeDocument

from document_preparation.cached import CachedMarkdownStorage
from document_preparation.content import (
    MarkdownDocumentContent,
    RenderableDocumentContent,
)
from document_preparation.exceptions import DocumentNotFoundError


@pytest.mark.asyncio
async def test_cached_markdown_storage_returns_cached_markdown() -> None:
    markdown_storage = MagicMock()
    markdown_storage.get = AsyncMock(
        return_value=MarkdownDocumentContent(content="# cached")
    )
    markdown_storage.set = AsyncMock()

    source_storage = MagicMock()
    source_storage.get = AsyncMock()

    renderer = MagicMock()
    renderer.render = AsyncMock()

    storage = CachedMarkdownStorage(markdown_storage, source_storage, renderer)
    document = FakeDocument(id=uuid4(), file_name="doc.pdf")

    loaded = await storage.get(document)

    assert loaded.content == "# cached"
    markdown_storage.get.assert_awaited_once_with(document)
    markdown_storage.set.assert_not_awaited()
    source_storage.get.assert_not_awaited()
    renderer.render.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_markdown_storage_builds_and_caches_on_miss() -> None:
    markdown_storage = MagicMock()
    markdown_storage.get = AsyncMock(side_effect=DocumentNotFoundError)
    markdown_storage.set = AsyncMock()

    source_document = object()
    source_storage = MagicMock()
    source_storage.get = AsyncMock(
        return_value=RenderableDocumentContent(content=source_document)
    )

    renderer = MagicMock()
    renderer.render = AsyncMock(return_value="# generated")

    storage = CachedMarkdownStorage(markdown_storage, source_storage, renderer)
    document = FakeDocument(id=uuid4(), file_name="doc.pdf")

    loaded = await storage.get(document)

    assert loaded.content == "# generated"
    markdown_storage.get.assert_awaited_once_with(document)
    source_storage.get.assert_awaited_once_with(document)
    renderer.render.assert_awaited_once_with(source_document)
    markdown_storage.set.assert_awaited_once()

    cached_document, cached_content = markdown_storage.set.await_args.args
    assert cached_document == document
    assert cached_content.content == "# generated"


@pytest.mark.asyncio
async def test_cached_markdown_storage_deletes_cached_markdown() -> None:
    markdown_storage = MagicMock()
    markdown_storage.delete = AsyncMock()
    source_storage = MagicMock()
    renderer = MagicMock()

    storage = CachedMarkdownStorage(markdown_storage, source_storage, renderer)
    document = FakeDocument(id=uuid4(), file_name="doc.pdf")

    await storage.delete(document)

    markdown_storage.delete.assert_awaited_once_with(document)
