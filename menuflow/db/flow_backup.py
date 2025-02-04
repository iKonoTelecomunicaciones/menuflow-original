import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Union

from asyncpg import Record
from attr import dataclass, ib
from mautrix.types import SerializableAttrs
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class FlowBackup(SerializableAttrs):
    db: ClassVar[Database] = fake_db

    id: int = ib(default=None)
    flow_id: int = ib(factory=int)
    flow: Dict[str, Any] = ib(factory=dict)
    created_at: datetime = ib(default=None)

    @property
    def values(self) -> tuple[int, str]:
        return (self.flow_id, json.dumps(self.flow))

    @classmethod
    def _from_row(cls, row: Record) -> Union["FlowBackup", None]:
        return cls(
            id=row["id"],
            flow_id=row["flow_id"],
            flow=json.loads(row["flow"]),
            created_at=row["created_at"],
        )

    @classmethod
    async def all_by_flow_id(cls, flow_id: int, limit: int = 10) -> list["FlowBackup"]:
        q = "SELECT id, flow_id, flow, created_at FROM flow_backup where flow_id=$1 ORDER BY created_at ASC limit $2"
        rows = await cls.db.fetch(q, flow_id, limit)
        if not rows:
            return []

        return [cls._from_row(row) for row in rows]

    @classmethod
    async def get_count_by_flow_id(cls, flow_id: int) -> int:
        q = "SELECT count(*) FROM flow_backup where flow_id=$1"
        return await cls.db.fetchval(q, flow_id)

    @classmethod
    async def delete_orldest_by_flow_id(cls, flow_id: int):
        q = "DELETE FROM flow_backup WHERE created_at = (SELECT MIN(created_at) FROM flow_backup WHERE flow_id=$1)"
        await cls.db.execute(q, flow_id)

    async def insert(self):
        q = "INSERT INTO flow_backup (flow_id, flow) VALUES ($1, $2)"
        await self.db.execute(q, *self.values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "flow_id": self.flow_id,
            "flow": self.flow,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
