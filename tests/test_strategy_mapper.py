from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.entities.unknown import UnknownDocument
from app.infrastructure.storages.minio_storage import (
    PreparedSpreadsheetStrategy,
    PreparedStrategyMapper,
    PreparedTextStrategy,
)


def _fake_guess(extension: str | None):
    """Подмена filetype.guess значением FakeKind(extension) либо None."""
    if extension is None:
        return lambda _data: None

    class FakeKind:
        pass

    FakeKind.extension = extension
    return lambda _data: FakeKind()


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


# --- Routing by content via filetype ---


def test_mapper_routes_spreadsheet_content_to_spreadsheet_strategy(
    mapper: PreparedStrategyMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("filetype.guess", _fake_guess("xlsx"))

    selected = mapper.pick(b"fake-xlsx")

    assert isinstance(selected, PreparedSpreadsheetStrategy)


def test_mapper_routes_text_content_to_text_strategy(
    mapper: PreparedStrategyMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("filetype.guess", _fake_guess("docx"))

    selected = mapper.pick(b"fake-docx")

    assert isinstance(selected, PreparedTextStrategy)


def test_mapper_routes_unknown_content_to_text_strategy(
    mapper: PreparedStrategyMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("filetype.guess", _fake_guess(None))

    selected = mapper.pick(b"who-knows")

    assert isinstance(selected, PreparedTextStrategy)


def test_mapper_supports_any_content(
    mapper: PreparedStrategyMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("filetype.guess", _fake_guess(None))

    assert mapper.supports(b"who-knows") is True


# --- Delegation through pick ---


def test_mapper_resolve_file_name_for_text_content(
    mapper: PreparedStrategyMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("filetype.guess", _fake_guess("docx"))
    document = UnknownDocument(id=uuid4(), file_name="contract.doc")

    assert mapper.resolve_file_name(document, b"fake-docx") == "contract.docx"


def test_mapper_resolve_file_name_for_spreadsheet_content(
    mapper: PreparedStrategyMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("filetype.guess", _fake_guess("xlsx"))
    document = UnknownDocument(id=uuid4(), file_name="report.xls")

    assert mapper.resolve_file_name(document, b"fake-xlsx") == "report.xlsx"


def test_mapper_is_already_prepared_by_content(
    mapper: PreparedStrategyMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("filetype.guess", _fake_guess("docx"))
    assert mapper.is_already_prepared(b"already-docx") is True

    monkeypatch.setattr("filetype.guess", _fake_guess("doc"))
    assert mapper.is_already_prepared(b"legacy-doc") is False


@pytest.mark.asyncio
async def test_mapper_delegates_convert_to_text_strategy(
    mapper_with_converters: tuple[PreparedStrategyMapper, AsyncMock, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapper, text_converter, _ = mapper_with_converters
    monkeypatch.setattr("filetype.guess", _fake_guess("doc"))
    document = UnknownDocument(id=uuid4(), file_name="contract.doc")

    assert await mapper.convert(document, b"raw-doc") == b"docx"

    text_converter.convert.assert_awaited_once_with("contract.doc", b"raw-doc")


@pytest.mark.asyncio
async def test_mapper_delegates_convert_to_spreadsheet_strategy(
    mapper_with_converters: tuple[PreparedStrategyMapper, AsyncMock, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapper, _, spreadsheet_converter = mapper_with_converters
    monkeypatch.setattr("filetype.guess", _fake_guess("xls"))
    document = UnknownDocument(id=uuid4(), file_name="report.xls")

    assert await mapper.convert(document, b"raw-xls") == b"xlsx"

    spreadsheet_converter.convert.assert_awaited_once_with("report.xls", b"raw-xls")
