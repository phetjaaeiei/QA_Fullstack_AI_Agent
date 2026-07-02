import os
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models import Base, User
from app.database import get_db
from app.main import app
from passlib.context import CryptContext

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://qa_brain:qa_brain_pass@localhost:5433/qa_brain_test"
)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def pytest_collection_modifyitems(items):
    """Set session loop scope on all asyncio tests so they share the session engine loop."""
    for item in items:
        if item.get_closest_marker("asyncio") is not None:
            item.add_marker(pytest.mark.asyncio(loop_scope="session"), append=False)


@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncSession:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
        from sqlalchemy import text
        async with session_factory() as cleanup:
            await cleanup.execute(text("DELETE FROM automation_scripts"))
            await cleanup.execute(text("DELETE FROM security_findings"))
            await cleanup.execute(text("DELETE FROM test_cases"))
            await cleanup.execute(text("DELETE FROM stories"))
            await cleanup.execute(text("DELETE FROM projects"))
            await cleanup.execute(text("DELETE FROM users"))
            await cleanup.commit()


@pytest.fixture(autouse=True)
async def override_get_db(db_session):
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def test_user(db_session):
    user = User(
        email="qa@extosoft.com",
        hashed_password=pwd_context.hash("testpassword"),
        role="qa_engineer",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def auth_token(test_user):
    from app.api.auth import create_access_token
    return create_access_token({"sub": test_user.email, "role": test_user.role})


@pytest.fixture
async def test_project(db_session):
    from app.models.project import Project
    project = Project(name="Test Project", jira_project_key="PROJ")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.fixture
async def test_story(db_session, test_project):
    from app.models.story import Story
    story = Story(
        project_id=test_project.id,
        jira_id="PROJ-123",
        title="User login",
        description="Login feature",
        status="In Progress",
    )
    db_session.add(story)
    await db_session.commit()
    await db_session.refresh(story)
    return story
