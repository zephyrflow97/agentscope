# -*- coding: utf-8 -*-
"""Session backend implementations for AgentScope platform.

This module provides abstract and concrete session storage backends
for persisting agent state across requests.
"""
import json
import os
from abc import ABC, abstractmethod
from typing import Any

from ..module import StateModule


class PlatformSessionBackend(ABC):
    """Abstract base class for platform session backends.

    Session backends handle persistence of agent state (memory, internal state)
    across multiple chat requests.
    """

    @abstractmethod
    async def save(
        self,
        session_id: str,
        **state_modules_mapping: StateModule,
    ) -> None:
        """Save session state for the given session ID.

        Args:
            session_id: Unique identifier for the session.
            **state_modules_mapping: Mapping of names to StateModule instances.
        """
        pass

    @abstractmethod
    async def load(
        self,
        session_id: str,
        allow_not_exist: bool = True,
        **state_modules_mapping: StateModule,
    ) -> None:
        """Load session state for the given session ID.

        Args:
            session_id: Unique identifier for the session.
            allow_not_exist: If True, don't raise error if session doesn't exist.
            **state_modules_mapping: Mapping of names to StateModule instances
                to load state into.
        """
        pass

    @abstractmethod
    async def exists(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            True if session exists, False otherwise.
        """
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Delete a session.

        Args:
            session_id: Unique identifier for the session.
        """
        pass


class RedisSessionBackend(PlatformSessionBackend):
    """Redis-based session backend.

    Stores session state in Redis for distributed access and persistence.
    """

    def __init__(
        self,
        url: str,
        prefix: str = "agentscope:session:",
        ttl: int | None = None,
    ) -> None:
        """Initialize Redis session backend.

        Args:
            url: Redis connection URL (e.g., "redis://localhost:6379/0").
            prefix: Key prefix for session data.
            ttl: Time-to-live for session data in seconds. None means no expiry.
        """
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "Redis support requires the 'redis' package. "
                "Install it with: pip install redis"
            )

        self._url = url
        self._prefix = prefix
        self._ttl = ttl
        self._redis: "aioredis.Redis | None" = None

    async def _get_client(self) -> "Any":
        """Get or create Redis client."""
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(self._url)
        return self._redis

    def _get_key(self, session_id: str) -> str:
        """Get Redis key for session."""
        return f"{self._prefix}{session_id}"

    async def save(
        self,
        session_id: str,
        **state_modules_mapping: StateModule,
    ) -> None:
        """Save session state to Redis."""
        client = await self._get_client()
        key = self._get_key(session_id)

        state_dicts = {
            name: state_module.state_dict()
            for name, state_module in state_modules_mapping.items()
        }

        data = json.dumps(state_dicts, ensure_ascii=False)

        if self._ttl:
            await client.setex(key, self._ttl, data)
        else:
            await client.set(key, data)

    async def load(
        self,
        session_id: str,
        allow_not_exist: bool = True,
        **state_modules_mapping: StateModule,
    ) -> None:
        """Load session state from Redis."""
        client = await self._get_client()
        key = self._get_key(session_id)

        data = await client.get(key)

        if data is None:
            if not allow_not_exist:
                raise ValueError(f"Session '{session_id}' not found in Redis")
            return

        states = json.loads(data)

        for name, state_module in state_modules_mapping.items():
            if name in states:
                state_module.load_state_dict(states[name])

    async def exists(self, session_id: str) -> bool:
        """Check if session exists in Redis."""
        client = await self._get_client()
        key = self._get_key(session_id)
        return await client.exists(key) > 0

    async def delete(self, session_id: str) -> None:
        """Delete session from Redis."""
        client = await self._get_client()
        key = self._get_key(session_id)
        await client.delete(key)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class DatabaseSessionBackend(PlatformSessionBackend):
    """Database-based session backend using SQLAlchemy.

    Stores session state in a SQL database for persistence.
    """

    def __init__(
        self,
        url: str,
        table_name: str = "agentscope_sessions",
    ) -> None:
        """Initialize database session backend.

        Args:
            url: SQLAlchemy database URL.
            table_name: Name of the table to store sessions.
        """
        self._url = url
        self._table_name = table_name
        self._engine: Any = None
        self._initialized = False

    async def _ensure_table(self) -> None:
        """Ensure the session table exists."""
        if self._initialized:
            return

        from sqlalchemy import (
            Column,
            DateTime,
            MetaData,
            String,
            Table,
            Text,
            func,
        )
        from sqlalchemy.ext.asyncio import create_async_engine

        self._engine = create_async_engine(self._url)

        metadata = MetaData()
        self._table = Table(
            self._table_name,
            metadata,
            Column("session_id", String(255), primary_key=True),
            Column("state_data", Text, nullable=False),
            Column(
                "created_at",
                DateTime,
                server_default=func.now(),
            ),
            Column(
                "updated_at",
                DateTime,
                server_default=func.now(),
                onupdate=func.now(),
            ),
        )

        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

        self._initialized = True

    async def save(
        self,
        session_id: str,
        **state_modules_mapping: StateModule,
    ) -> None:
        """Save session state to database."""
        await self._ensure_table()

        from sqlalchemy import insert
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        state_dicts = {
            name: state_module.state_dict()
            for name, state_module in state_modules_mapping.items()
        }
        data = json.dumps(state_dicts, ensure_ascii=False)

        # Use upsert pattern
        async with self._engine.begin() as conn:
            # Check dialect for appropriate upsert syntax
            dialect = self._engine.dialect.name

            if dialect == "postgresql":
                stmt = pg_insert(self._table).values(
                    session_id=session_id,
                    state_data=data,
                ).on_conflict_do_update(
                    index_elements=["session_id"],
                    set_={"state_data": data},
                )
            elif dialect == "sqlite":
                stmt = sqlite_insert(self._table).values(
                    session_id=session_id,
                    state_data=data,
                ).on_conflict_do_update(
                    index_elements=["session_id"],
                    set_={"state_data": data},
                )
            else:
                # Fallback: delete then insert
                from sqlalchemy import delete
                await conn.execute(
                    delete(self._table).where(
                        self._table.c.session_id == session_id
                    )
                )
                stmt = insert(self._table).values(
                    session_id=session_id,
                    state_data=data,
                )

            await conn.execute(stmt)

    async def load(
        self,
        session_id: str,
        allow_not_exist: bool = True,
        **state_modules_mapping: StateModule,
    ) -> None:
        """Load session state from database."""
        await self._ensure_table()

        from sqlalchemy import select

        async with self._engine.begin() as conn:
            result = await conn.execute(
                select(self._table.c.state_data).where(
                    self._table.c.session_id == session_id
                )
            )
            row = result.fetchone()

        if row is None:
            if not allow_not_exist:
                raise ValueError(
                    f"Session '{session_id}' not found in database"
                )
            return

        states = json.loads(row[0])

        for name, state_module in state_modules_mapping.items():
            if name in states:
                state_module.load_state_dict(states[name])

    async def exists(self, session_id: str) -> bool:
        """Check if session exists in database."""
        await self._ensure_table()

        from sqlalchemy import select, func

        async with self._engine.begin() as conn:
            result = await conn.execute(
                select(func.count()).where(
                    self._table.c.session_id == session_id
                )
            )
            count = result.scalar()

        return count > 0

    async def delete(self, session_id: str) -> None:
        """Delete session from database."""
        await self._ensure_table()

        from sqlalchemy import delete

        async with self._engine.begin() as conn:
            await conn.execute(
                delete(self._table).where(
                    self._table.c.session_id == session_id
                )
            )

    async def close(self) -> None:
        """Close database connection."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._initialized = False


class FileSessionBackend(PlatformSessionBackend):
    """File-based session backend for local development.

    Stores session state in JSON files on the local filesystem.
    """

    def __init__(self, save_dir: str = "./sessions") -> None:
        """Initialize file session backend.

        Args:
            save_dir: Directory to store session files.
        """
        self._save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)

    def _get_path(self, session_id: str) -> str:
        """Get file path for session."""
        return os.path.join(self._save_dir, f"{session_id}.json")

    async def save(
        self,
        session_id: str,
        **state_modules_mapping: StateModule,
    ) -> None:
        """Save session state to file."""
        path = self._get_path(session_id)

        state_dicts = {
            name: state_module.state_dict()
            for name, state_module in state_modules_mapping.items()
        }

        with open(path, "w", encoding="utf-8", errors="surrogatepass") as f:
            json.dump(state_dicts, f, ensure_ascii=False)

    async def load(
        self,
        session_id: str,
        allow_not_exist: bool = True,
        **state_modules_mapping: StateModule,
    ) -> None:
        """Load session state from file."""
        path = self._get_path(session_id)

        if not os.path.exists(path):
            if not allow_not_exist:
                raise ValueError(f"Session file '{path}' not found")
            return

        with open(path, "r", encoding="utf-8", errors="surrogatepass") as f:
            states = json.load(f)

        for name, state_module in state_modules_mapping.items():
            if name in states:
                state_module.load_state_dict(states[name])

    async def exists(self, session_id: str) -> bool:
        """Check if session file exists."""
        return os.path.exists(self._get_path(session_id))

    async def delete(self, session_id: str) -> None:
        """Delete session file."""
        path = self._get_path(session_id)
        if os.path.exists(path):
            os.remove(path)

    async def close(self) -> None:
        """No-op for file backend."""
        pass


def create_session_backend(
    backend_type: str,
    url: str | None = None,
    **kwargs: Any,
) -> PlatformSessionBackend:
    """Factory function to create a session backend.

    Args:
        backend_type: Type of backend ("redis", "database", "file").
        url: Connection URL for redis/database backends.
        **kwargs: Additional arguments for the backend constructor.

    Returns:
        PlatformSessionBackend instance.

    Raises:
        ValueError: If backend_type is unknown.
    """
    if backend_type == "redis":
        if not url:
            raise ValueError("Redis backend requires a URL")
        return RedisSessionBackend(url=url, **kwargs)

    elif backend_type == "database":
        if not url:
            raise ValueError("Database backend requires a URL")
        return DatabaseSessionBackend(url=url, **kwargs)

    elif backend_type == "file":
        save_dir = kwargs.get("save_dir", "./sessions")
        return FileSessionBackend(save_dir=save_dir)

    else:
        raise ValueError(f"Unknown session backend type: {backend_type}")
