import asyncio
import io
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
from app.domain.ports.prepared_strategy import IPreparedStrategy
from app.domain.ports.storage import IDocumentStorage
from app.infrastructure.taskiq.tasks import docling_to_markdown


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
            extension = _guess_extension(raw.content)
            prepared = await self._strategy.prepare(document, raw.content, extension)
            await self._prepared_storage.set(
                document=document,
                content=BinaryDocumentContent(content=prepared.content),
            )
            return prepared
        extension = _guess_extension(cached.content)
        return PreparedDocumentContent(
            content=cached.content,
            file_name=self._strategy.resolve_file_name(document, extension),
        )

    @override
    async def delete(self, document: BaseDocument) -> None:
        await self._prepared_storage.delete(document)
