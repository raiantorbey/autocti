"""Create or reset the default admin user.

Usage:
    python -m backend.scripts.create_admin
    python -m backend.scripts.create_admin --username admin --password s3cret

Idempotent: re-running updates the password.
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from backend.core.logging import logger, setup_logging
from backend.core.security import hash_password
from backend.db.postgres import async_session_factory, init_db
from backend.models.models import User


async def _run(username: str, password: str, email: str) -> None:
    await init_db()
    async with async_session_factory() as s:
        q = await s.execute(select(User).where(User.username == username))
        u = q.scalar_one_or_none()
        if u:
            u.hashed_password = hash_password(password)
            u.role = "admin"
            u.is_active = True
            logger.info(f"Updated existing admin: {username}")
        else:
            u = User(
                username=username,
                email=email,
                hashed_password=hash_password(password),
                role="admin",
                is_active=True,
            )
            s.add(u)
            logger.info(f"Created admin: {username}")
        await s.commit()


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser()
    p.add_argument("--username", default="admin")
    p.add_argument("--password", default="admin123")
    p.add_argument("--email", default="admin@autocti.local")
    args = p.parse_args()
    asyncio.run(_run(args.username, args.password, args.email))


if __name__ == "__main__":
    main()
