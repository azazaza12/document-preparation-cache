from typing import Protocol
from uuid import UUID


class Document(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def file_name(self) -> str: ...
