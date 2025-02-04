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
    await conn.execute("CREATE INDEX ind_route_room_client ON route (room, client)")
    await conn.execute(
        "ALTER TABLE route ADD CONSTRAINT FK_room_route FOREIGN KEY (room) references room (id)"
    )
    await conn.execute(
        "ALTER TABLE route ADD CONSTRAINT FK_client_route FOREIGN KEY (client) references client (id)"
    )

    # Drop old columns from room table
    await conn.execute("ALTER TABLE room DROP COLUMN node_id")
    await conn.execute("ALTER TABLE room DROP COLUMN state")


@upgrade_table.register(description="Add stack field to route table")
async def upgrade_v3(conn: Connection) -> None:
    # Add stack column to route table
    await conn.execute("ALTER TABLE route ADD COLUMN stack JSONB NOT NULL DEFAULT '{}'::jsonb")


@upgrade_table.register(description="Add flow table and flow column to client table")
async def upgrade_v4(conn: Connection) -> None:
    # Add flow column to client table
    await conn.execute("ALTER TABLE client ADD COLUMN flow INT")

    # Create flow table
    await conn.execute(
        """CREATE TABLE flow (
            id          SERIAL PRIMARY KEY,
            flow        JSONB DEFAULT '{}'::jsonb
        )"""
    )

    # Add foreign key to client table
    await conn.execute(
        "ALTER TABLE client ADD CONSTRAINT FK_flow_client FOREIGN KEY (flow) references flow (id)"
    )


@upgrade_table.register(description="Add enable column to client table")
async def upgrade_v5(conn: Connection) -> None:
    await conn.execute("ALTER TABLE client ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE")


@upgrade_table.register(description="Add new table flow_backup")
async def upgrade_v6(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE flow_backup (
            id          SERIAL PRIMARY KEY,
            flow_id     INT NOT NULL,
            flow        JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at  TIMESTAMP  WITH TIME ZONE DEFAULT now()
        )"""
    )
