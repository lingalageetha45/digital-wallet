from typing import Any, Optional
from fastapi import HTTPException, status


class AppException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[Any] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class InsufficientBalanceError(AppException):
    def __init__(self, message: str = "Insufficient wallet balance."):
        super().__init__(
            code="INSUFFICIENT_BALANCE",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class WalletFrozenError(AppException):
    def __init__(self, message: str = "Wallet is frozen."):
        super().__init__(
            code="WALLET_FROZEN",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class WalletClosedError(AppException):
    def __init__(self, message: str = "Wallet is closed."):
        super().__init__(
            code="WALLET_CLOSED",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class InvalidTransferError(AppException):
    def __init__(self, message: str = "Invalid transfer request."):
        super().__init__(
            code="INVALID_TRANSFER",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class DuplicateTransactionError(AppException):
    def __init__(self, message: str = "Duplicate transaction detected."):
        super().__init__(
            code="DUPLICATE_TRANSACTION",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class TransactionLimitExceededError(AppException):
    def __init__(self, message: str = "Transaction limit exceeded."):
        super().__init__(
            code="TRANSACTION_LIMIT_EXCEEDED",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class DuplicateIdempotencyKeyError(AppException):
    def __init__(self, message: str = "Duplicate idempotency key."):
        super().__init__(
            code="DUPLICATE_IDEMPOTENCY_KEY",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidRefundError(AppException):
    def __init__(self, message: str = "Invalid refund request."):
        super().__init__(
            code="INVALID_REFUND",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class SuspiciousTransactionError(AppException):
    def __init__(self, message: str = "Transaction flagged as suspicious."):
        super().__init__(
            code="SUSPICIOUS_TRANSACTION",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Not authorized."):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenError(AppException):
    def __init__(self, message: str = "Forbidden."):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found."):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ConflictError(AppException):
    def __init__(self, message: str = "Conflict."):
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


def app_exception_handler(request, exc: AppException):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                **({"details": exc.details} if exc.details else {}),
            },
        },
    )