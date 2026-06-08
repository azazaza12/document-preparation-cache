from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.entities.single_supplier import SingleSupplierDocument
from app.domain.entities.unknown import UnknownDocument
from app.infrastructure.storages.minio_storage import (
    PreparedSpreadsheetStrategy,
    PreparedStrategyMapper,
    PreparedTextStrategy,
)


@pytest.fixture
def mapper_with_converters() -> tuple[PreparedStrategyMapper, AsyncMock, AsyncMock]:
    text_converter = AsyncMock()
    text_converter.convert = AsyncMock(return_value=b"docx")
    spreadsheet_converter = AsyncMock()
    spreadsheet_converter.convert = AsyncMock(return_value=b"xlsx")
    mapper = PreparedStrategyMapper(
        [
            PreparedSpreadsheetStrategy(spreadsheet_converter),
            PreparedTextStrategy(text_converter),
        ]
    )
    return mapper, text_converter, spreadsheet_converter


@pytest.fixture
def mapper(
    mapper_with_converters: tuple[PreparedStrategyMapper, AsyncMock, AsyncMock],
) -> PreparedStrategyMapper:
    return mapper_with_converters[0]


def test_mapper_supports_text_document(
    mapper: PreparedStrategyMapper,
) -> None:
    text_document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")

    assert mapper.supports(text_document) is True


def test_mapper_routes_text_document_to_text_strategy(
    mapper: PreparedStrategyMapper,
) -> None:
    document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")

    assert mapper.resolve_file_name(document) == "contract.docx"
    assert mapper.is_already_prepared(document) is False


@pytest.mark.asyncio
async def test_mapper_delegates_convert_to_text_strategy(
    mapper_with_converters: tuple[PreparedStrategyMapper, AsyncMock, AsyncMock],
) -> None:
    mapper, text_converter, _ = mapper_with_converters

    text_document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")

    assert await mapper.convert(text_document, b"raw-doc") == b"docx"

    text_converter.convert.assert_awaited_once_with("contract.doc", b"raw-doc")


# --- Extension based routing via filetype for any document ---


def test_mapper_routes_unknown_xlsx_to_spreadsheet_strategy(
    mapper: PreparedStrategyMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = UnknownDocument(id=uuid4(), file_name="report.xls")

    class FakeKind:
        extension = "xlsx"

    monkeypatch.setattr("filetype.guess", lambda data: FakeKind())

    selected = mapper.pick_strategy(doc, b"fake-xlsx")
    assert isinstance(selected, PreparedSpreadsheetStrategy)


def test_mapper_routes_unknown_docx_to_text_strategy(
    mapper: PreparedStrategyMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = UnknownDocument(id=uuid4(), file_name="contract.doc")

    class FakeKind:
        extension = "docx"

    monkeypatch.setattr("filetype.guess", lambda data: FakeKind())

    selected = mapper.pick_strategy(doc, b"fake-docx")
    assert isinstance(selected, PreparedTextStrategy)
