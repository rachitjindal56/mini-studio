from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import ValidationError
from app.middleware.logger.logging import file_logger

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response

        except HTTPException as http_exc:
            # Handle HTTP exceptions (4xx, 5xx status codes)
            file_logger.error(f"HTTPException: {http_exc.detail}")
            return JSONResponse(
                status_code=http_exc.status_code,
                content={"error": http_exc.detail}
            )

        except ValidationError as val_exc:
            # Handle Pydantic validation errors
            file_logger.error(f"ValidationError: {val_exc.errors()}")
            return JSONResponse(
                status_code=422,
                content={"error": "Validation Error", "detail": val_exc.errors()}
            )

        except Exception as exc:
            # Handle any other unexpected errors
            file_logger.error(f"Internal Server Error: {str(exc)}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "detail": str(exc)
                }
            )