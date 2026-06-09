from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.documents.prepared_strategy import (
    PreparedSpreadsheetStrategy,
    PreparedStrategyMapper,
    PreparedTextStrategy,
)
from app.domain.entities.unknown import UnknownDocument


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


def test_mapper_routes_spreadsheet_extension_to_spreadsheet_strategy(
    mapper: PreparedStrategyMapper,
) -> None:
    assert isinstance(mapper.pick(".xlsx"), PreparedSpreadsheetStrategy)


def test_mapper_routes_text_extension_to_text_strategy(
    mapper: PreparedStrategyMapper,
) -> None:
    assert isinstance(mapper.pick(".docx"), PreparedTextStrategy)


def test_mapper_raises_for_unsupported_extension(
    mapper: PreparedStrategyMapper,
) -> None:
    with pytest.raises(ValueError, match="No prepared strategy"):
        mapper.pick(None)


def test_mapper_does_not_support_unrecognized_extension(
    mapper: PreparedStrategyMapper,
) -> None:
    assert mapper.supports(None) is False


def test_mapper_resolve_file_name_for_text_extension(
    mapper: PreparedStrategyMapper,
) -> None:
    document = UnknownDocument(id=uuid4(), file_name="contract.doc")

    assert mapper.resolve_file_name(document, ".docx") == "contract.docx"


def test_mapper_resolve_file_name_for_spreadsheet_extension(
    mapper: PreparedStrategyMapper,
) -> None:
    document = UnknownDocument(id=uuid4(), file_name="report.xls")

    assert mapper.resolve_file_name(document, ".xlsx") == "report.xlsx"


@pytest.mark.asyncio
async def test_mapper_prepare_returns_raw_when_already_prepared(
    mapper_with_converters: tuple[PreparedStrategyMapper, AsyncMock, AsyncMock],
) -> None:
    mapper, text_converter, _ = mapper_with_converters
    document = UnknownDocument(id=uuid4(), file_name="contract.docx")

    prepared = await mapper.prepare(document, b"already-docx", ".docx")

    assert prepared.content == b"already-docx"
    assert prepared.file_name == "contract.docx"
    text_converter.convert.assert_not_awaited()


@pytest.mark.asyncio
async def test_mapper_prepare_converts_via_text_strategy(
    mapper_with_converters: tuple[PreparedStrategyMapper, AsyncMock, AsyncMock],
) -> None:
    mapper, text_converter, spreadsheet_converter = mapper_with_converters
    document = UnknownDocument(id=uuid4(), file_name="contract.odt")

    prepared = await mapper.prepare(document, b"raw-odt", ".odt")

    assert prepared.content == b"docx"
    assert prepared.file_name == "contract.docx"
    text_converter.convert.assert_awaited_once_with("contract.odt", b"raw-odt")
    spreadsheet_converter.convert.assert_not_awaited()


@pytest.mark.asyncio
async def test_mapper_prepare_converts_via_spreadsheet_strategy(
    mapper_with_converters: tuple[PreparedStrategyMapper, AsyncMock, AsyncMock],
) -> None:
    mapper, text_converter, spreadsheet_converter = mapper_with_converters
    document = UnknownDocument(id=uuid4(), file_name="report.xls")

    prepared = await mapper.prepare(document, b"raw-xls", ".xls")

    assert prepared.content == b"xlsx"
    assert prepared.file_name == "report.xlsx"
    spreadsheet_converter.convert.assert_awaited_once_with("report.xls", b"raw-xls")
    text_converter.convert.assert_not_awaited()
