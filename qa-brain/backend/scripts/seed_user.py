"""Create or update a QA Brain user. There is no signup endpoint by design —
this is an internal tool, so accounts are provisioned by an admin.

Usage:
    python -m scripts.seed_user qa@extosoft.com --password Test1234! --role qa_engineer
"""
import argparse
import asyncio

from passlib.context import CryptContext
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed_user(email: str, password: str, role: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            user.hashed_password = pwd_context.hash(password)
            user.role = role
            print(f"Updated existing user {email} (role={role})")
        else:
            db.add(User(email=email, hashed_password=pwd_context.hash(password), role=role))
            print(f"Created new user {email} (role={role})")

        await db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", default="qa_engineer", choices=["qa_engineer", "qa_lead", "admin"])
    args = parser.parse_args()

    asyncio.run(seed_user(args.email, args.password, args.role))
