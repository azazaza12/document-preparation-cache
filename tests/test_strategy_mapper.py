from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.entities.imcp.document import ExcelIMCPDocument
from app.domain.entities.single_supplier import SingleSupplierDocument
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
def mapper(mapper_with_converters: tuple[PreparedStrategyMapper, AsyncMock, AsyncMock]) -> PreparedStrategyMapper:
    return mapper_with_converters[0]


def test_mapper_supports_text_and_spreadsheet_documents(
    mapper: PreparedStrategyMapper,
) -> None:
    text_document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")
    spreadsheet_document = ExcelIMCPDocument(id=uuid4(), file_name="imcp.xls")

    assert mapper.supports(text_document) is True
    assert mapper.supports(spreadsheet_document) is True


def test_mapper_routes_text_document_to_text_strategy(
    mapper: PreparedStrategyMapper,
) -> None:
    document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")

    assert mapper.resolve_file_name(document) == "contract.docx"
    assert mapper.is_already_prepared(document) is False


def test_mapper_routes_spreadsheet_document_to_spreadsheet_strategy(
    mapper: PreparedStrategyMapper,
) -> None:
    document = ExcelIMCPDocument(id=uuid4(), file_name="imcp.xls")

    assert mapper.resolve_file_name(document) == "imcp.xlsx"
    assert mapper.is_already_prepared(document) is False


@pytest.mark.asyncio
async def test_mapper_delegates_convert_to_matching_strategy(
    mapper_with_converters: tuple[PreparedStrategyMapper, AsyncMock, AsyncMock],
) -> None:
    mapper, text_converter, spreadsheet_converter = mapper_with_converters

    spreadsheet_document = ExcelIMCPDocument(id=uuid4(), file_name="imcp.xls")
    text_document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")

    assert await mapper.convert(spreadsheet_document, b"raw-xls") == b"xlsx"
    assert await mapper.convert(text_document, b"raw-doc") == b"docx"

    spreadsheet_converter.convert.assert_awaited_once_with("imcp.xls", b"raw-xls")
    text_converter.convert.assert_awaited_once_with("contract.doc", b"raw-doc")


def test_mapper_raises_when_no_strategy_supports_document() -> None:
    unsupported_strategy = MagicMock()
    unsupported_strategy.supports.return_value = False
    mapper = PreparedStrategyMapper([unsupported_strategy])
    document = SingleSupplierDocument(id=uuid4(), file_name="contract.doc")

    try:
        mapper.resolve_file_name(document)
    except ValueError as exc:
        assert "No prepared strategy" in str(exc)
    else:
        pytest.fail("Expected ValueError")
