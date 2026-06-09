from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application import DocumentNotFoundError
from app.domain.entities.single_supplier import SingleSupplierDocument
from app.domain.entities.unknown import UnknownDocument
from app.domain.ports.documents import BinaryDocumentContent
from app.infrastructure.storages.minio_storage import (
    CachedPreparedDocumentStorage,
    PreparedSpreadsheetStrategy,
    PreparedStrategyMapper,
    PreparedTextStrategy,
)


def _patch_guess(monkeypatch: pytest.MonkeyPatch, extension: str | None) -> None:
    """Подмена filetype.guess значением FakeKind(extension) либо None."""
    if extension is None:
        monkeypatch.setattr("filetype.guess", lambda _data: None)
        return

    class FakeKind:
        pass

    FakeKind.extension = extension
    monkeypatch.setattr("filetype.guess", lambda _data: FakeKind())


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

    assert loaded.content == b"cached-docx"
    assert loaded.file_name == "contract.docx"
    prepared_storage.get.assert_awaited_once_with(document)
    raw_storage.get.assert_not_awaited()
    converter.convert.assert_not_awaited()
    prepared_storage.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepared_text_cache_miss_converts_doc_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_guess(monkeypatch, "doc")
    prepared_storage = MagicMock()
    prepared_storage.get = AsyncMock(side_effect=DocumentNotFoundError)
    prepared_storage.set = AsyncMock()

    raw_storage = MagicMock()
    raw_storage.get = AsyncMock(return_value=BinaryDocumentContent(content=b"raw-doc"))

    converter = AsyncMock()
    converter.convert.return_value = b"converted-docx"
    strategy = PreparedTextStrategy(converter)

    storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, strategy)
    document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")

    loaded = await storage.get(document)

    assert loaded.content == b"converted-docx"
    assert loaded.file_name == "contract.docx"
    raw_storage.get.assert_awaited_once_with(document)
    converter.convert.assert_awaited_once_with("contract.doc", b"raw-doc")
    prepared_storage.set.assert_awaited_once()

    set_kwargs = prepared_storage.set.await_args.kwargs
    assert set_kwargs["document"] == document
    assert set_kwargs["content"].content == b"converted-docx"


@pytest.mark.asyncio
async def test_prepared_text_cache_miss_docx_skips_converter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_guess(monkeypatch, "docx")
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

    assert loaded.content == b"docx-bytes"
    assert loaded.file_name == "contract.docx"
    converter.convert.assert_not_awaited()
    prepared_storage.set.assert_awaited_once()

    assert prepared_storage.set.await_args.kwargs["content"].content == b"docx-bytes"


@pytest.mark.asyncio
async def test_prepared_spreadsheet_cache_miss_converts_xls_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_guess(monkeypatch, "xls")
    prepared_storage = MagicMock()
    prepared_storage.get = AsyncMock(side_effect=DocumentNotFoundError)
    prepared_storage.set = AsyncMock()

    raw_storage = MagicMock()
    raw_storage.get = AsyncMock(return_value=BinaryDocumentContent(content=b"raw-xls"))

    converter = AsyncMock()
    converter.convert.return_value = b"converted-xlsx"
    strategy = PreparedSpreadsheetStrategy(converter)

    storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, strategy)
    document = SingleSupplierDocument(id=uuid4(), file_name="imcp.xls")

    loaded = await storage.get(document)

    assert loaded.content == b"converted-xlsx"
    assert loaded.file_name == "imcp.xlsx"
    converter.convert.assert_awaited_once_with("imcp.xls", b"raw-xls")
    prepared_storage.set.assert_awaited_once()

    set_kwargs = prepared_storage.set.await_args.kwargs
    assert set_kwargs["document"] == document
    assert set_kwargs["content"].content == b"converted-xlsx"


@pytest.mark.asyncio
async def test_prepared_spreadsheet_cache_miss_xlsx_skips_converter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_guess(monkeypatch, "xlsx")
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

    assert loaded.content == b"xlsx-bytes"
    assert loaded.file_name == "imcp.xlsx"
    converter.convert.assert_not_awaited()
    prepared_storage.set.assert_awaited_once()

    assert prepared_storage.set.await_args.kwargs["content"].content == b"xlsx-bytes"


# --- Storage driven by the mapper: routing happens by content, not by name ---


def _mapper() -> tuple[PreparedStrategyMapper, AsyncMock, AsyncMock]:
    text_converter = AsyncMock()
    text_converter.convert.return_value = b"converted-docx"
    spreadsheet_converter = AsyncMock()
    spreadsheet_converter.convert.return_value = b"converted-xlsx"
    mapper = PreparedStrategyMapper(
        [
            PreparedSpreadsheetStrategy(spreadsheet_converter),
            PreparedTextStrategy(text_converter),
        ]
    )
    return mapper, text_converter, spreadsheet_converter


@pytest.mark.asyncio
async def test_mapper_cache_miss_routes_xlsx_content_to_spreadsheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_guess(monkeypatch, "xls")
    prepared_storage = MagicMock()
    prepared_storage.get = AsyncMock(side_effect=DocumentNotFoundError)
    prepared_storage.set = AsyncMock()

    raw_storage = MagicMock()
    raw_storage.get = AsyncMock(return_value=BinaryDocumentContent(content=b"raw-xls"))

    mapper, text_converter, spreadsheet_converter = _mapper()
    storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, mapper)
    document = UnknownDocument(id=uuid4(), file_name="report.xls")

    loaded = await storage.get(document)

    assert loaded.content == b"converted-xlsx"
    assert loaded.file_name == "report.xlsx"
    spreadsheet_converter.convert.assert_awaited_once_with("report.xls", b"raw-xls")
    text_converter.convert.assert_not_awaited()


@pytest.mark.asyncio
async def test_mapper_cache_miss_routes_odt_content_to_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_guess(monkeypatch, "odt")
    prepared_storage = MagicMock()
    prepared_storage.get = AsyncMock(side_effect=DocumentNotFoundError)
    prepared_storage.set = AsyncMock()

    raw_storage = MagicMock()
    raw_storage.get = AsyncMock(return_value=BinaryDocumentContent(content=b"raw-odt"))

    mapper, text_converter, spreadsheet_converter = _mapper()
    storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, mapper)
    document = UnknownDocument(id=uuid4(), file_name="contract.odt")

    loaded = await storage.get(document)

    assert loaded.content == b"converted-docx"
    assert loaded.file_name == "contract.docx"
    text_converter.convert.assert_awaited_once_with("contract.odt", b"raw-odt")
    spreadsheet_converter.convert.assert_not_awaited()


@pytest.mark.asyncio
async def test_mapper_cache_hit_resolves_file_name_from_cached_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # На cache-hit имя выхода берётся по содержимому закэшированных байтов,
    # поэтому xlsx из кэша не получает текстовое имя .docx.
    _patch_guess(monkeypatch, "xlsx")
    prepared_storage = MagicMock()
    prepared_storage.get = AsyncMock(
        return_value=BinaryDocumentContent(content=b"cached-xlsx")
    )
    prepared_storage.set = AsyncMock()

    raw_storage = MagicMock()
    raw_storage.get = AsyncMock()

    mapper, text_converter, spreadsheet_converter = _mapper()
    storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, mapper)
    document = UnknownDocument(id=uuid4(), file_name="report.bin")

    loaded = await storage.get(document)

    assert loaded.content == b"cached-xlsx"
    assert loaded.file_name == "report.xlsx"
    raw_storage.get.assert_not_awaited()
    text_converter.convert.assert_not_awaited()
    spreadsheet_converter.convert.assert_not_awaited()
    prepared_storage.set.assert_not_awaited()


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
