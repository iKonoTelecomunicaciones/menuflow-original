from asyncpg import Connection
from mautrix.util.async_db import UpgradeTable

upgrade_table = UpgradeTable()


@upgrade_table.register(description="Initial revision")
async def upgrade_v1(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE room (
            id          SERIAL PRIMARY KEY,
            room_id     TEXT NOT NULL,
            variables   JSON,
            node_id     TEXT,
            state       TEXT
        )"""
    )
    await conn.execute(
        """CREATE TABLE "user" (
            id          SERIAL PRIMARY KEY,
            mxid        TEXT NOT NULL
        )"""
    )
    await conn.execute(
        """CREATE TABLE client (
            id           TEXT    PRIMARY KEY,
            homeserver   TEXT    NOT NULL,
            access_token TEXT    NOT NULL,
            device_id    TEXT    NOT NULL,

            next_batch TEXT NOT NULL,
            filter_id  TEXT NOT NULL,

            autojoin BOOLEAN NOT NULL
        )"""
    )

    await conn.execute("ALTER TABLE room ADD CONSTRAINT idx_unique_room_id UNIQUE (room_id)")


@upgrade_table.register(description="Add new table route")
async def upgrade_v2(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE route (
            id          SERIAL PRIMARY KEY,
            room        INT NOT NULL,
            client      TEXT NOT NULL,
            node_id     TEXT,
            state       TEXT,
            variables   JSON
        )"""
    )
    await conn.execute(
        "ALTER TABLE route ADD CONSTRAINT FK_room_route FOREIGN KEY (room) references room (id)"
    )
    await conn.execute(
        "ALTER TABLE route ADD CONSTRAINT FK_client_route FOREIGN KEY (client) references client (id)"
    )

    # Drop old columns from room table
    await conn.execute("ALTER TABLE room DROP COLUMN node_id")
    await conn.execute("ALTER TABLE room DROP COLUMN state")
