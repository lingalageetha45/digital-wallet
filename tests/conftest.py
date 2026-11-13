import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models.user import Role, User, UserRole
from app.models.system import TransactionLimit
from decimal import Decimal


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        # seed roles
        for r in UserRole:
            session.add(Role(name=r, description=r.value))
        await session.commit()

        role = (await session.execute(
            __import__("sqlalchemy").select(Role).where(Role.name == UserRole.CUSTOMER)
        )).scalar_one()
        admin_role = (await session.execute(
            __import__("sqlalchemy").select(Role).where(Role.name == UserRole.SUPER_ADMIN)
        )).scalar_one()

        customer = User(
            email="customer@test.com",
            hashed_password=get_password_hash("Test@12345"),
            full_name="Test Customer",
            role_id=role.id,
            is_active=True,
            is_verified=True,
        )
        admin = User(
            email="admin@test.com",
            hashed_password=get_password_hash("Admin@12345"),
            full_name="Test Admin",
            role_id=admin_role.id,
            is_active=True,
            is_verified=True,
        )
        session.add_all([customer, admin])
        session.add(
            TransactionLimit(
                max_transaction_amount=Decimal("100000"),
                daily_transfer_limit=Decimal("50000"),
                daily_withdrawal_limit=Decimal("20000"),
                max_transactions_per_day=50,
                suspicious_amount_threshold=Decimal("10000"),
            )
        )
        await session.commit()
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "customer@test.com", "password": "Test@12345"},
    )
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(client):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "Admin@12345"},
    )
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}