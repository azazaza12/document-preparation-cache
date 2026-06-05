import asyncio
import io
from typing import override

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
)
from app.domain.ports.storage import IDocumentStorage
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


class MinioDoclingToMarkdownDocumentStorage(IDocumentStorage[MarkdownDocumentContent]):
    def __init__(self, storage: MinioDoclingDocumentStorage) -> None:
        self._storage = storage

    @override
    async def set(
        self, document: BaseDocument, content: MarkdownDocumentContent
    ) -> None: ...

    @override
    async def get(self, document: BaseDocument) -> MarkdownDocumentContent:
        docling_content = await self._storage.get(document)
        result = await docling_to_markdown.kiq(
            document=docling_content.content.model_dump()
        )
        markdown = await result.wait_result()
        return MarkdownDocumentContent(content=markdown.return_value)

    @override
    async def delete(self, document: BaseDocument) -> None:
        await self._storage.delete(document)


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
