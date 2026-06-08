import asyncio
import io
from abc import ABC, abstractmethod
from typing import override
from pathlib import Path

from docling_core.types.doc.document import DoclingDocument
from minio import Minio
from minio.error import S3Error

from app.application import DocumentNotFoundError
from app.config import StorageSettings
from app.domain.entities import BaseDocument
from app.domain.entities.imcp.document import ExcelIMCPDocument
from app.domain.ports.docx_converter import IToDocxConverter
from app.domain.ports.documents import (
    BinaryDocumentContent,
    DoclingDocumentContent,
    MarkdownDocumentContent,
    PreparedDocumentContent,
    PreparedContent,
)
from app.domain.ports.storage import IDocumentStorage
from app.domain.ports.xlsx_converter import IToXlsxConverter
from app.infrastructure.taskiq.tasks import docling_to_markdown



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
    def supports(self, document: BaseDocument) -> bool: ...

    @abstractmethod
    def resolve_file_name(self, document: BaseDocument) -> str: ...

    @abstractmethod
    def is_already_prepared(self, document: BaseDocument) -> bool: ...

    @abstractmethod
    async def convert(self, document: BaseDocument, data: bytes) -> bytes: ...


class PreparedTextStrategy(IPreparedStrategy):
    def __init__(self, to_docx_converter: IToDocxConverter) -> None:
        self._to_docx_converter = to_docx_converter

    @override
    def supports(self, document: BaseDocument) -> bool:
        return not isinstance(document, ExcelIMCPDocument)

    @override
    def resolve_file_name(self, document: BaseDocument) -> str:
        raw_file_name = document.file_name
        suffix = Path(raw_file_name).suffix.lower()
        if suffix in {".pdf", ".docx"}:
            return raw_file_name
        return str(Path(raw_file_name).with_suffix(".docx"))

    @override
    def is_already_prepared(self, document: BaseDocument) -> bool:
        return Path(document.file_name).suffix.lower() in {".pdf", ".docx"}

    @override
    async def convert(self, document: BaseDocument, data: bytes) -> bytes:
        return await self._to_docx_converter.convert(document.file_name, data)


class PreparedSpreadsheetStrategy(IPreparedStrategy):
    def __init__(self, to_xlsx_converter: IToXlsxConverter) -> None:
        self._to_xlsx_converter = to_xlsx_converter

    @override
    def supports(self, document: BaseDocument) -> bool:
        return isinstance(document, ExcelIMCPDocument)

    @override
    def resolve_file_name(self, document: BaseDocument) -> str:
        raw_file_name = document.file_name
        suffix = Path(raw_file_name).suffix.lower()
        if suffix == ".xlsx":
            return raw_file_name
        return str(Path(raw_file_name).with_suffix(".xlsx"))

    @override
    def is_already_prepared(self, document: BaseDocument) -> bool:
        return Path(document.file_name).suffix.lower() == ".xlsx"

    @override
    async def convert(self, document: BaseDocument, data: bytes) -> bytes:
        return await self._to_xlsx_converter.convert(document.file_name, data)


class PreparedStrategyMapper(IPreparedStrategy):
    def __init__(self, strategies: list[IPreparedStrategy]) -> None:
        self._strategies = strategies

    def _pick(self, document: BaseDocument) -> IPreparedStrategy:
        for strategy in self._strategies:
            if strategy.supports(document):
                return strategy
        msg = f"No prepared strategy for {type(document).__name__}"
        raise ValueError(msg)

    @override
    def supports(self, document: BaseDocument) -> bool:
        return any(strategy.supports(document) for strategy in self._strategies)

    @override
    def resolve_file_name(self, document: BaseDocument) -> str:
        return self._pick(document).resolve_file_name(document)

    @override
    def is_already_prepared(self, document: BaseDocument) -> bool:
        return self._pick(document).is_already_prepared(document)

    @override
    async def convert(self, document: BaseDocument, data: bytes) -> bytes:
        return await self._pick(document).convert(document, data)


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
            content=BinaryDocumentContent(content=content.content.content),
        )

    @override
    async def get(self, document: BaseDocument) -> PreparedDocumentContent:
        try:
            cached = await self._prepared_storage.get(document)
            content_bytes = cached.content
        except DocumentNotFoundError:
            raw = await self._raw_storage.get(document)
            if self._strategy.is_already_prepared(document):
                content_bytes = raw.content
            else:
                content_bytes = await self._strategy.convert(document, raw.content)
            await self._prepared_storage.set(
                document=document,
                content=BinaryDocumentContent(content=content_bytes),
            )
        return PreparedDocumentContent(
            content=PreparedContent(
                content=content_bytes,
                file_name=self._strategy.resolve_file_name(document),
            )
        )

    @override
    async def delete(self, document: BaseDocument) -> None:
        await self._prepared_storage.delete(document)
