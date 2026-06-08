from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application import DocumentNotFoundError
from app.domain.entities.single_supplier import SingleSupplierDocument
from app.domain.ports.documents import BinaryDocumentContent
from app.infrastructure.storages.minio_storage import (
    CachedPreparedDocumentStorage,
    PreparedSpreadsheetStrategy,
    PreparedTextStrategy,
)


@pytest.mark.asyncio
async def test_prepared_text_cache_hit_returns_resolved_file_name() -> None:
    prepared_storage = MagicMock()
    prepared_storage.get = AsyncMock(
        return_value=BinaryDocumentContent(content=b"cached-docx")
    )
    prepared_storage.set = AsyncMock()

    raw_storage = MagicMock()
    raw_storage.get = AsyncMock()

    converter = AsyncMock()
    strategy = PreparedTextStrategy(converter)

    storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, strategy)
    document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")

    loaded = await storage.get(document)

    assert loaded.content.content == b"cached-docx"
    assert loaded.content.file_name == "contract.docx"
    prepared_storage.get.assert_awaited_once_with(document)
    raw_storage.get.assert_not_awaited()
    converter.convert.assert_not_awaited()
    prepared_storage.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepared_text_cache_miss_converts_doc_and_caches() -> None:
    prepared_storage = MagicMock()
    prepared_storage.get = AsyncMock(side_effect=DocumentNotFoundError)
    prepared_storage.set = AsyncMock()

    raw_storage = MagicMock()
    raw_storage.get = AsyncMock(
        return_value=BinaryDocumentContent(content=b"raw-doc")
    )

    converter = AsyncMock()
    converter.convert.return_value = b"converted-docx"
    strategy = PreparedTextStrategy(converter)

    storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, strategy)
    document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")

    loaded = await storage.get(document)

    assert loaded.content.content == b"converted-docx"
    assert loaded.content.file_name == "contract.docx"
    raw_storage.get.assert_awaited_once_with(document)
    converter.convert.assert_awaited_once_with("contract.doc", b"raw-doc")
    prepared_storage.set.assert_awaited_once()

    set_kwargs = prepared_storage.set.await_args.kwargs
    assert set_kwargs["document"] == document
    assert set_kwargs["content"].content == b"converted-docx"


@pytest.mark.asyncio
async def test_prepared_text_cache_miss_docx_skips_converter() -> None:
    prepared_storage = MagicMock()
    prepared_storage.get = AsyncMock(side_effect=DocumentNotFoundError)
    prepared_storage.set = AsyncMock()

    raw_storage = MagicMock()
    raw_storage.get = AsyncMock(
        return_value=BinaryDocumentContent(content=b"docx-bytes")
    )

    converter = AsyncMock()
    strategy = PreparedTextStrategy(converter)

    storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, strategy)
    document = SingleSupplierDocument(id=uuid4(), file_name="contract.docx")

    loaded = await storage.get(document)

    assert loaded.content.content == b"docx-bytes"
    assert loaded.content.file_name == "contract.docx"
    converter.convert.assert_not_awaited()
    prepared_storage.set.assert_awaited_once()

    assert prepared_storage.set.await_args.kwargs["content"].content == b"docx-bytes"


@pytest.mark.asyncio
async def test_prepared_spreadsheet_cache_miss_converts_xls_and_caches() -> None:
    prepared_storage = MagicMock()
    prepared_storage.get = AsyncMock(side_effect=DocumentNotFoundError)
    prepared_storage.set = AsyncMock()

    raw_storage = MagicMock()
    raw_storage.get = AsyncMock(
        return_value=BinaryDocumentContent(content=b"raw-xls")
    )

    converter = AsyncMock()
    converter.convert.return_value = b"converted-xlsx"
    strategy = PreparedSpreadsheetStrategy(converter)

    storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, strategy)
    document = SingleSupplierDocument(id=uuid4(), file_name="imcp.xls")

    loaded = await storage.get(document)

    assert loaded.content.content == b"converted-xlsx"
    assert loaded.content.file_name == "imcp.xlsx"
    converter.convert.assert_awaited_once_with("imcp.xls", b"raw-xls")
    prepared_storage.set.assert_awaited_once()

    set_kwargs = prepared_storage.set.await_args.kwargs
    assert set_kwargs["document"] == document
    assert set_kwargs["content"].content == b"converted-xlsx"


@pytest.mark.asyncio
async def test_prepared_spreadsheet_cache_miss_xlsx_skips_converter() -> None:
    prepared_storage = MagicMock()
    prepared_storage.get = AsyncMock(side_effect=DocumentNotFoundError)
    prepared_storage.set = AsyncMock()

    raw_storage = MagicMock()
    raw_storage.get = AsyncMock(
        return_value=BinaryDocumentContent(content=b"xlsx-bytes")
    )

    converter = AsyncMock()
    strategy = PreparedSpreadsheetStrategy(converter)

    storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, strategy)
    document = SingleSupplierDocument(id=uuid4(), file_name="imcp.xlsx")

    loaded = await storage.get(document)

    assert loaded.content.content == b"xlsx-bytes"
    assert loaded.content.file_name == "imcp.xlsx"
    converter.convert.assert_not_awaited()
    prepared_storage.set.assert_awaited_once()

    assert prepared_storage.set.await_args.kwargs["content"].content == b"xlsx-bytes"


@pytest.mark.asyncio
async def test_cached_prepared_document_storage_deletes_prepared() -> None:
    prepared_storage = MagicMock()
    prepared_storage.delete = AsyncMock()
    raw_storage = MagicMock()
    converter = AsyncMock()

    storage = CachedPreparedDocumentStorage(
        prepared_storage,
        raw_storage,
        PreparedTextStrategy(converter),
    )
    document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")

    await storage.delete(document)

    prepared_storage.delete.assert_awaited_once_with(document)
