import json
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Union

from asyncpg import Record
from attr import dataclass, ib
from mautrix.types import SerializableAttrs
from mautrix.util.async_db import Database

from ..config import Config
from .flow_backup import FlowBackup

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Flow(SerializableAttrs):
    db: ClassVar[Database] = fake_db

    id: int = ib(default=None)
    flow: Dict[str, Any] = ib(factory=dict)

    @property
    def values(self) -> Dict[str, Any]:
        return json.dumps(self.flow)

    @classmethod
    def _from_row(cls, row: Record) -> Union["Flow", None]:
        return cls(id=row["id"], flow=json.loads(row["flow"]))

    @classmethod
    async def all(cls) -> list[Dict]:
        q = "SELECT id, flow FROM flow"
        rows = await cls.db.fetch(q)
        if not rows:
            return []

        return [cls._from_row(row).serialize() for row in rows]

    @classmethod
    async def get_by_id(cls, id: int) -> Union["Flow", None]:
        q = "SELECT id, flow FROM flow WHERE id=$1"
        row = await cls.db.fetchrow(q, id)

        if not row:
            return

        return cls._from_row(row)

    @classmethod
    async def get_by_mxid(cls, mxid: str) -> Union["Flow", None]:
        q = "SELECT f.id, f.flow FROM flow as f JOIN client as c ON f.id = c.flow WHERE c.id = $1"
        row = await cls.db.fetchrow(q, mxid)

        if not row:
            return

        return cls._from_row(row)

    async def insert(self) -> int:
        q = "INSERT INTO flow (flow) VALUES ($1)"
        await self.db.execute(q, self.values)
        return await self.db.fetchval("SELECT MAX(id) FROM flow")

    async def update(self) -> None:
        q = "UPDATE flow SET flow=$1 WHERE id=$2"
        await self.db.execute(q, self.values, self.id)

    async def backup_flow(self, config: Config) -> None:
        backup_count = await FlowBackup.get_count_by_flow_id(self.id)
        if backup_count >= config["menuflow.backup_limit"]:
            await FlowBackup.delete_orldest_by_flow_id(self.id)

        await FlowBackup(flow_id=self.id, flow=self.flow).insert()
