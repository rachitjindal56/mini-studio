import uuid
from datetime import datetime

from fastapi import Request

from app.middleware.logger.logging import logger
from app.services.audit_logs.audit_log_model import AuditLogModel
from app.services.audit_logs.audit_log_repository import MiddlewareRepository
from utility.utils import current_utc_time
from app.middleware.logger.logging import RequestContextManager
AUDIT_LOG_COLLECTION = MiddlewareRepository()

async def initialize_request(request: Request):
    """Initialize request logging data in MongoDB"""
    # Get the request_id from the context manager
    request_id = RequestContextManager.get_request_id()
    
    # Get hash_key from request headers or request.state
    hash_key_headers = request.headers.get('X-Hash-Key', 'no-hash-key')
    hash_key = getattr(request.state, 'hash_key', hash_key_headers)
    
    # Ensure request.state has the same request_id and hash_key
    request.state.req_id = request_id
    request.state.hash_key = hash_key
    request.state.start_time = current_utc_time()
    body = {}
    try:
        if request.headers.get('content-type') == 'application/json':
            body = await request.json()
        else:
            body = {}
    except Exception as e:
        logger.warning(f"Could not parse request body as JSON: {e}")
        body = {}

    audit_log = AuditLogModel(
        req_uuid=request_id,
        hash_key=hash_key,  
        user_id=request.state.user_id if hasattr(request.state, "user_id") else None,
        client_code=(
            request.state.client_code if hasattr(request.state, "client_code") else None
        ),
        http_method=request.method,
        url=str(request.url),
        ip=request.client.host,
        query_params=dict(request.query_params),
        body=body,
        headers=dict(request.headers),
        created_at=current_utc_time(),
    )

    try:
        result = await AUDIT_LOG_COLLECTION.insert_one(
            audit_log.model_dump(exclude_none=True)
        )
        logger.info(f"Initial log inserted with request id: {request_id}")
    except Exception as e:
        logger.error(f"Failed to log initial request to MongoDB: {e}")

    return audit_log

async def audit_log_middleware(request: Request, call_next):
    """Main middleware function to update request code and response time"""
    try:
        # Step 1: Initialize
        audit_log = await initialize_request(request)

        # Step 2: Call the API
        response = await call_next(request)

        # Step 3: Update response data
        response_time = (current_utc_time() - request.state.start_time).total_seconds() * 1000

        # Create partial update model with just the response fields
        update_model = AuditLogModel(
            req_uuid=str(request.state.req_id),
            hash_key=request.state.hash_key,  
            http_method=audit_log.http_method,
            url=audit_log.url,
            ip=audit_log.ip,
            body=audit_log.body,
            headers=audit_log.headers,
            created_at=audit_log.created_at,
            response_code=response.status_code,
            response_time_ms=str(response_time),
        )

        try:
            # Update the existing document with response data
            await AUDIT_LOG_COLLECTION.update_one(
                {"req_uuid": str(request.state.req_id)},
                {
                    "$set": update_model.model_dump(
                        include={"response_code", "response_time_ms"}
                    )
                },
            )
            logger.info("Log updated with response data")
        except Exception as e:
            logger.error(f"Failed to update log in MongoDB: {e}")

        return response
    finally:
        # Clear the request context only after all middleware operations are complete
        RequestContextManager.clear_request_context()