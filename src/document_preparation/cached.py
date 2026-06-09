import asyncio
import io
from abc import ABC, abstractmethod
from pathlib import Path
from typing import override

import filetype
from docling_core.types.doc.document import DoclingDocument
from minio import Minio
from minio.error import S3Error

from app.application import DocumentNotFoundError
from app.config import StorageSettings
from app.domain.entities import BaseDocument
from app.domain.ports.documents import (
    BinaryDocumentContent,
    DoclingDocumentContent,
    MarkdownDocumentContent,
    PreparedDocumentContent,
)
from app.domain.ports.docx_converter import IToDocxConverter
from app.domain.ports.storage import IDocumentStorage
from app.domain.ports.xlsx_converter import IToXlsxConverter
from app.infrastructure.taskiq.tasks import docling_to_markdown


_SPREADSHEET_EXTENSIONS = frozenset({".xls", ".xlsx", ".xlsm", ".ods"})
_TEXT_READY_EXTENSIONS = frozenset({".pdf", ".docx"})
_TEXT_SOURCE_EXTENSIONS = frozenset({".pdf", ".docx", ".docm", ".doc", ".odt", ".rtf"})


def _guess_extension(data: bytes) -> str | None:
    kind = filetype.guess(data)
    return f".{kind.extension}" if kind else None


class MinioStorageClient:
    def __init__(self, settings: StorageSettings, bucket_name: str) -> None:
        self._bucket_name = bucket_name
        self._client = Minio(
            endpoint=settings.ENDPOINT,
            access_key=settings.ACCESS_KEY,
            secret_key=settings.SECRET_KEY,
            secure=settings.SECURE,
        )

    async def upload(self, data: bytes, object_name: str) -> None:
        def _upload() -> None:
            self._client.put_object(
                bucket_name=self._bucket_name,
                object_name=object_name,
                data=io.BytesIO(data),
                length=len(data),
            )

        await asyncio.to_thread(_upload)

    async def download(self, object_id: str) -> bytes:
        def _download() -> bytes:
            response = None
            try:
                response = self._client.get_object(
                    bucket_name=self._bucket_name,
                    object_name=object_id,
                )
                return response.read()
            except S3Error as exc:
                if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                    raise DocumentNotFoundError from exc
                raise
            finally:
                if response is not None:
                    response.close()
                    response.release_conn()

        return await asyncio.to_thread(_download)

    async def delete(self, object_id: str) -> None:
        def _delete() -> None:
            self._client.remove_object(
                bucket_name=self._bucket_name,
                object_name=object_id,
            )

        await asyncio.to_thread(_delete)


class MinioBinaryDocumentStorage(IDocumentStorage[BinaryDocumentContent]):
    def __init__(self, client: MinioStorageClient) -> None:
        self._client = client

    @override
    async def set(self, document: BaseDocument, content: BinaryDocumentContent) -> None:
        await self._client.upload(content.content, str(document.id))

    @override
    async def get(self, document: BaseDocument) -> BinaryDocumentContent:
        data = await self._client.download(str(document.id))
        return BinaryDocumentContent(content=data)

    @override
    async def delete(self, document: BaseDocument) -> None:
        await self._client.delete(str(document.id))


class MinioDoclingDocumentStorage(IDocumentStorage[DoclingDocumentContent]):
    def __init__(self, client: MinioStorageClient) -> None:
        self._client = client

    @override
    async def set(
        self, document: BaseDocument, content: DoclingDocumentContent
    ) -> None:
        await self._client.upload(
            content.content.model_dump_json().encode(), str(document.id)
        )

    @override
    async def get(self, document: BaseDocument) -> DoclingDocumentContent:

        data = await self._client.download(str(document.id))
        return DoclingDocumentContent(content=DoclingDocument.model_validate_json(data))

    @override
    async def delete(self, document: BaseDocument) -> None:
        await self._client.delete(str(document.id))


class MinioMarkdownDocumentStorage(IDocumentStorage[MarkdownDocumentContent]):
    def __init__(self, client: MinioStorageClient) -> None:
        self._client = client

    @override
    async def set(
        self,
        document: BaseDocument,
        content: MarkdownDocumentContent,
    ) -> None:
        await self._client.upload(content.content.encode(), str(document.id))

    @override
    async def get(self, document: BaseDocument) -> MarkdownDocumentContent:
        data = await self._client.download(str(document.id))
        return MarkdownDocumentContent(content=data.decode())

    @override
    async def delete(self, document: BaseDocument) -> None:
        await self._client.delete(str(document.id))


class CachedDoclingMarkdownStorage(IDocumentStorage[MarkdownDocumentContent]):
    def __init__(
        self,
        document_storage_md: MinioMarkdownDocumentStorage,
        docling_document_storage: MinioDoclingDocumentStorage,
    ) -> None:
        self._document_storage_md = document_storage_md
        self._docling_document_storage = docling_document_storage

    @override
    async def set(
        self, document: BaseDocument, content: MarkdownDocumentContent
    ) -> None:
        await self._document_storage_md.set(document, content)

    @override
    async def get(self, document: BaseDocument) -> MarkdownDocumentContent:
        try:
            return await self._document_storage_md.get(document)
        except DocumentNotFoundError:
            docling_doc = await self._docling_document_storage.get(document)
            result = await docling_to_markdown.kiq(
                document=docling_doc.content.model_dump()
            )
            markdown_task_result = await result.wait_result()
            content = MarkdownDocumentContent(content=markdown_task_result.return_value)
            await self._document_storage_md.set(document, content)
            return content

    @override
    async def delete(self, document: BaseDocument) -> None:
        await self._document_storage_md.delete(document)


class IPreparedStrategy(ABC):
    @abstractmethod
    def supports(self, content: bytes) -> bool: ...

    @abstractmethod
    def resolve_file_name(self, document: BaseDocument, content: bytes) -> str: ...

    @abstractmethod
    async def prepare(
        self, document: BaseDocument, raw: bytes
    ) -> PreparedDocumentContent: ...


class PreparedTextStrategy(IPreparedStrategy):
    def __init__(self, to_docx_converter: IToDocxConverter) -> None:
        self._to_docx_converter = to_docx_converter

    @override
    def supports(self, content: bytes) -> bool:
        return _guess_extension(content) in _TEXT_SOURCE_EXTENSIONS

    @override
    def resolve_file_name(self, document: BaseDocument, content: bytes) -> str:
        raw_file_name = document.file_name
        suffix = Path(raw_file_name).suffix.lower()
        if suffix in _TEXT_READY_EXTENSIONS:
            return raw_file_name
        return str(Path(raw_file_name).with_suffix(".docx"))

    @override
    async def prepare(
        self, document: BaseDocument, raw: bytes
    ) -> PreparedDocumentContent:
        if _guess_extension(raw) in _TEXT_READY_EXTENSIONS:
            content = raw
        else:
            content = await self._to_docx_converter.convert(document.file_name, raw)
        return PreparedDocumentContent(
            content=content,
            file_name=self.resolve_file_name(document, content),
        )


class PreparedSpreadsheetStrategy(IPreparedStrategy):
    def __init__(self, to_xlsx_converter: IToXlsxConverter) -> None:
        self._to_xlsx_converter = to_xlsx_converter

    @override
    def supports(self, content: bytes) -> bool:
        return _guess_extension(content) in _SPREADSHEET_EXTENSIONS

    @override
    def resolve_file_name(self, document: BaseDocument, content: bytes) -> str:
        raw_file_name = document.file_name
        suffix = Path(raw_file_name).suffix.lower()
        if suffix == ".xlsx":
            return raw_file_name
        return str(Path(raw_file_name).with_suffix(".xlsx"))

    @override
    async def prepare(
        self, document: BaseDocument, raw: bytes
    ) -> PreparedDocumentContent:
        if _guess_extension(raw) == ".xlsx":
            content = raw
        else:
            content = await self._to_xlsx_converter.convert(document.file_name, raw)
        return PreparedDocumentContent(
            content=content,
            file_name=self.resolve_file_name(document, content),
        )


class PreparedStrategyMapper(IPreparedStrategy):
    def __init__(self, strategies: list[IPreparedStrategy]) -> None:
        self._strategies = strategies

    def pick(self, content: bytes) -> IPreparedStrategy:
        for strategy in self._strategies:
            if strategy.supports(content):
                return strategy
        msg = "No prepared strategy for given content"
        raise ValueError(msg)

    @override
    def supports(self, content: bytes) -> bool:
        return any(strategy.supports(content) for strategy in self._strategies)

    @override
    def resolve_file_name(self, document: BaseDocument, content: bytes) -> str:
        return self.pick(content).resolve_file_name(document, content)

    @override
    async def prepare(
        self, document: BaseDocument, raw: bytes
    ) -> PreparedDocumentContent:
        return await self.pick(raw).prepare(document, raw)


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
    async def set(
        self, document: BaseDocument, content: PreparedDocumentContent
    ) -> None:
        await self._prepared_storage.set(
            document=document,
            content=BinaryDocumentContent(content=content.content),
        )

    @override
    async def get(self, document: BaseDocument) -> PreparedDocumentContent:
        try:
            cached = await self._prepared_storage.get(document)
        except DocumentNotFoundError:
            raw = await self._raw_storage.get(document)
            prepared = await self._strategy.prepare(document, raw.content)
            await self._prepared_storage.set(
                document=document,
                content=BinaryDocumentContent(content=prepared.content),
            )
            return prepared
        return PreparedDocumentContent(
            content=cached.content,
            file_name=self._strategy.resolve_file_name(document, cached.content),
        )

    @override
    async def delete(self, document: BaseDocument) -> None:
        await self._prepared_storage.delete(document)
