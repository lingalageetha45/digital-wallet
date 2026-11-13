from fastapi import APIRouter
from app.api.v1.endpoints import auth, wallets, transactions, admin, notifications

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(wallets.router, prefix="/wallets", tags=["Wallets"])
api_router.include_router(transactions.router, tags=["Transactions"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])