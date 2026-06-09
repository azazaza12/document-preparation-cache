from pathlib import Path
from typing import TYPE_CHECKING, override

from app.domain.ports.documents import PreparedDocumentContent
from app.domain.ports.docx_converter import IToDocxConverter
from app.domain.ports.prepared_strategy import IPreparedStrategy
from app.domain.ports.xlsx_converter import IToXlsxConverter


if TYPE_CHECKING:
    from app.domain.entities import BaseDocument


_TEXT_SOURCE_EXTENSIONS = frozenset({".pdf", ".doc", ".docx", ".odt", ".rtf"})
_SPREADSHEET_SOURCE_EXTENSIONS = frozenset({".xls", ".xlsx", ".ods"})
_PREPARED_EXTENSIONS = frozenset({".pdf", ".docx", ".xlsx"})


class PreparedTextStrategy(IPreparedStrategy):
    def __init__(self, to_docx_converter: IToDocxConverter) -> None:
        self._to_docx_converter = to_docx_converter

    @override
    def supports(self, extension: str | None) -> bool:
        return extension in _TEXT_SOURCE_EXTENSIONS

    @override
    def resolve_file_name(self, document: BaseDocument, extension: str | None) -> str:
        raw_file_name = document.file_name
        suffix = Path(raw_file_name).suffix.lower()
        if suffix in _PREPARED_EXTENSIONS:
            return raw_file_name
        return str(Path(raw_file_name).with_suffix(".docx"))

    @override
    async def prepare(
        self, document: BaseDocument, raw: bytes, extension: str | None
    ) -> PreparedDocumentContent:
        if extension in _PREPARED_EXTENSIONS:
            content = raw
        else:
            content = await self._to_docx_converter.convert(document.file_name, raw)
        return PreparedDocumentContent(
            content=content,
            file_name=self.resolve_file_name(document, extension),
        )


class PreparedSpreadsheetStrategy(IPreparedStrategy):
    def __init__(self, to_xlsx_converter: IToXlsxConverter) -> None:
        self._to_xlsx_converter = to_xlsx_converter

    @override
    def supports(self, extension: str | None) -> bool:
        return extension in _SPREADSHEET_SOURCE_EXTENSIONS

    @override
    def resolve_file_name(self, document: BaseDocument, extension: str | None) -> str:
        raw_file_name = document.file_name
        suffix = Path(raw_file_name).suffix.lower()
        if suffix in _PREPARED_EXTENSIONS:
            return raw_file_name
        return str(Path(raw_file_name).with_suffix(".xlsx"))

    @override
    async def prepare(
        self, document: BaseDocument, raw: bytes, extension: str | None
    ) -> PreparedDocumentContent:
        if extension in _PREPARED_EXTENSIONS:
            content = raw
        else:
            content = await self._to_xlsx_converter.convert(document.file_name, raw)
        return PreparedDocumentContent(
            content=content,
            file_name=self.resolve_file_name(document, extension),
        )


class PreparedStrategyMapper(IPreparedStrategy):
    def __init__(self, strategies: list[IPreparedStrategy]) -> None:
        self._strategies = strategies

    def pick(self, extension: str | None) -> IPreparedStrategy:
        for strategy in self._strategies:
            if strategy.supports(extension):
                return strategy
        msg = "No prepared strategy for given content"
        raise ValueError(msg)

    @override
    def supports(self, extension: str | None) -> bool:
        return any(strategy.supports(extension) for strategy in self._strategies)

    @override
    def resolve_file_name(self, document: BaseDocument, extension: str | None) -> str:
        return self.pick(extension).resolve_file_name(document, extension)

    @override
    async def prepare(
        self, document: BaseDocument, raw: bytes, extension: str | None
    ) -> PreparedDocumentContent:
        return await self.pick(extension).prepare(document, raw, extension)
