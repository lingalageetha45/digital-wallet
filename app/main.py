from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import AppException, app_exception_handler
from app.core.security import get_password_hash
from app.db.session import engine, AsyncSessionLocal
from app.db.base import Base
from app.models.user import Role, User, UserRole
from app.models.system import TransactionLimit
from app.api.v1.router import api_router
from decimal import Decimal


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Seed roles
        for role_enum in UserRole:
            result = await db.execute(select(Role).where(Role.name == role_enum))
            if not result.scalar_one_or_none():
                db.add(Role(name=role_enum, description=role_enum.value.replace("_", " ").title()))
        await db.commit()

        # Seed super admin
        result = await db.execute(select(User).where(User.email == settings.FIRST_SUPERUSER_EMAIL))
        if not result.scalar_one_or_none():
            role_result = await db.execute(select(Role).where(Role.name == UserRole.SUPER_ADMIN))
            role = role_result.scalar_one()
            admin = User(
                email=settings.FIRST_SUPERUSER_EMAIL,
                hashed_password=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
                full_name=settings.FIRST_SUPERUSER_FULL_NAME,
                role_id=role.id,
                is_active=True,
                is_verified=True,
            )
            db.add(admin)
            await db.commit()

        # Seed transaction limits
        result = await db.execute(select(TransactionLimit).limit(1))
        if not result.scalar_one_or_none():
            db.add(
                TransactionLimit(
                    max_transaction_amount=Decimal(str(settings.MAX_TRANSACTION_AMOUNT)),
                    daily_transfer_limit=Decimal(str(settings.DAILY_TRANSFER_LIMIT)),
                    daily_withdrawal_limit=Decimal(str(settings.DAILY_WITHDRAWAL_LIMIT)),
                    max_transactions_per_day=settings.MAX_TRANSACTIONS_PER_DAY,
                    suspicious_amount_threshold=Decimal(str(settings.SUSPICIOUS_AMOUNT_THRESHOLD)),
                )
            )
            await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Secure Digital Wallet & Transaction Processing Platform",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppException, app_exception_handler)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred.",
            },
        },
    )


app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}