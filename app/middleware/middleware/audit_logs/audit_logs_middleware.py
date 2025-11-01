from fastapi import Request

from app.middleware.logger.logging import file_logger
from app.services.audit_logs.audit_log_model import AuditLogModel, AuditLogUpdateModel
from app.services.audit_logs.audit_log_service import AuditLogService
from utility.utils import current_utc_time
from app.middleware.logger.RequestContextManager import RequestContextManager

DEFAULT_CLIENT_CODE = "common"
audit_log_service = AuditLogService()

async def initialize_request(request: Request):
    """Initialize request logging data in MongoDB"""
    # Get the request_id from the context manager
    request_id = RequestContextManager.get_request_id()
    hash_key_headers = request.headers.get('X-Hash-Key', 'no-hash-key')
    # hash_key = getattr(request.state, 'hash_key', hash_key_headers)

    audit_log = AuditLogModel(
        request_id=request_id,
        user_id=RequestContextManager.get_user_id(),
        http_method=request.method,
        url=str(request.url),
        ip=getattr(request.client, 'host', 'unknown'),
        query_params=dict(request.query_params),
        body=await request.json() if (await request.body()) else {},
        headers=dict(request.headers)
    )

    try:
        client_code = RequestContextManager.get_client_code()
        if client_code is None or client_code == '':
            file_logger.warning("Client code is missing in the request body, using default collection")
            client_code = DEFAULT_CLIENT_CODE
            
        result = await audit_log_service.create_audit_log(
            client_code,
            audit_log
        )
        file_logger.info(f"Initial log inserted with request id: {request_id}")
    except Exception as e:
        file_logger.error(f"Failed to log initial request to MongoDB: {e}")

    return audit_log


async def audit_log_middleware(request: Request, call_next):
    """Main middleware function to update request code and response time"""
    try:
        start_time = current_utc_time()
        # Step 1: Initialize
        audit_log = await initialize_request(request)

        # Step 2: Call the API
        response = await call_next(request)

        # Step 3: Update response data
        response_time = (current_utc_time() - start_time).total_seconds() * 1000

        # Create partial update model with just the response fields
        update_model = AuditLogUpdateModel(
            request_id=audit_log.request_id,
            response_code=response.status_code,
            response_time_ms=str(response_time),
        )

        try:
            client_code = RequestContextManager.get_client_code()
            if client_code is None or client_code == '':
                file_logger.warning("Client code is missing in the request body, using default collection")
                client_code = DEFAULT_CLIENT_CODE

            await audit_log_service.update_audit_log(
                client_code,
                {"request_id": update_model.request_id},
                {
                    "$set": {
                        "response_code": update_model.response_code,
                        "response_time_ms": update_model.response_time_ms
                    }
                },
            )
            file_logger.info(f"Route: {request.url}, Response Time: {response_time}ms")
        except Exception as e:
            file_logger.error(f"Failed to update log in MongoDB: {e}")

        return response
    finally:
        # Clear the request context only after all middleware operations are complete
        RequestContextManager.clear_request_context()
