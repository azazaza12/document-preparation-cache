from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class FakeDocument:
    id: UUID
    file_name: str
