import os
import functools
import contextvars
import time
import uuid
import logging
import json
from typing import Callable, Dict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from utility.utils import current_utc_time


log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

file_logger = logging.getLogger("request_file_logger")
file_logger.setLevel(logging.INFO)

request_id_var = contextvars.ContextVar('request_id', default='') # context variable to store request_id

class RequestContextManager:
    _context = {}

    @classmethod
    def set_request_context(cls, request_id: str):
        request_id_var.set(request_id)

    @classmethod
    def get_request_id(cls) -> str:
        return request_id_var.get()

    @classmethod
    def get_logger(cls) -> logging.Logger:
        return file_logger

    @classmethod
    def clear_request_context(cls):
        request_id_var.set('')

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "ts": current_utc_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            "lv": record.levelname,
            "id": RequestContextManager.get_request_id(),
            "hash_key": getattr(record, 'hash_key', 'no-hash-key'),
            "sIp": record.sIp if hasattr(record, 'sIp') else '',
            "fl": record.filename,
            "fn": record.funcName,
            "ln": record.lineno,
            "message_content": getattr(record, 'message_content', record.getMessage()),
            "ctx": record.ctx if hasattr(record, 'ctx') else ''
        }
        return json.dumps(log_record)

def get_datewise_log_file():
    current_date = current_utc_time().strftime('%Y-%m-%d')
    return os.path.join(log_dir, f"request_logs_{current_date}.json")

if not file_logger.handlers:
    datewise_file = get_datewise_log_file()
    file_handler = logging.FileHandler(datewise_file)
    file_handler.setFormatter(JsonFormatter())
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JsonFormatter())
    file_logger.addHandler(file_handler)
    file_logger.addHandler(console_handler)
    file_logger.propagate = False

# New logger configuration for verbaflo
logger = logging.getLogger("verbaflo")
logger.setLevel(logging.INFO)

# Create console handler for app logs
console_handler_app = logging.StreamHandler()
console_handler_app.setLevel(logging.INFO)

# Create formatter for app logs
formatter_app = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler_app.setFormatter(formatter_app)

# Add handlers to app logger
logger.addHandler(console_handler_app)

class RequestResponseLogger:
    def __init__(self):
        self.logger = logging.getLogger('request_response')

    def log_request(self, request: Request, request_id: str):
        log_entry = {
            'timestamp': current_utc_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            'request_id': request_id,
            'method': request.method,
            'url': str(request.url),
            'client_host': request.client.host if request.client else None,
            'headers': dict(request.headers)
        }
        self.logger.info(f"Incoming Request: {json.dumps(log_entry)}")

    def log_response(self, request: Request, response: Response, duration: float, request_id: str):
        log_entry = {
            'timestamp': current_utc_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            'request_id': request_id,
            'method': request.method,
            'url': str(request.url),
            'status_code': response.status_code,
            'duration_ms': duration,
            'response_headers': dict(response.headers)
        }
        self.logger.info(f"Outgoing Response: {json.dumps(log_entry)}")

class ErrorLogger:
    def __init__(self):
        self.logger = logging.getLogger('error')

    def log_error(self, error: Exception, request_id: str, additional_info: Dict = None):
        log_entry = {
            'timestamp': current_utc_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            'request_id': request_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'additional_info': additional_info
        }
        self.logger.error(f"Error Occurred: {json.dumps(log_entry)}")

class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, request_response_logger: RequestResponseLogger):
        super().__init__(app)
        self.request_response_logger = request_response_logger
        self.error_logger = ErrorLogger()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request_id and get hash_key
        request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        hash_key = request.headers.get('X-Hash-Key', 'no-hash-key')
        
        # Set both request.state values
        request.state.req_id = request_id
        request.state.hash_key = hash_key
        RequestContextManager.set_request_context(request_id)

        sIp = request.client.host if request.client else "unknown"
        
        try:
            file_logger.info("Request started", extra={
                "sIp": sIp,
                "ctx": "REQUEST",
                "message_content": f"{request.method} {request.url}",
                "request_id": request_id,
                "hash_key": hash_key
            })

            self.request_response_logger.log_request(request, request_id)

            start_time = time.time()
            response = await call_next(request)
            duration = (time.time() - start_time) * 1000
            
            file_logger.info("Request completed", extra={
                "sIp": sIp,
                "ctx": "RESPONSE",
                "message_content": f"{request.method} {request.url} completed in {duration:.2f}ms with status {response.status_code}",
                "request_id": request_id,
                "hash_key": hash_key
            })
            
            self.request_response_logger.log_response(request, response, duration, request_id)
            return response
        except Exception as e:
            file_logger.exception("Request failed", extra={
                "sIp": sIp,
                "ctx": "ERROR",
                "message_content": str(e),
                "request_id": request_id,
                "hash_key": hash_key
            })
            self.error_logger.log_error(e, request_id)
            raise

def log_database_operation(operation: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            request_id = RequestContextManager.get_request_id()
            try:
                result = await func(*args, **kwargs)
                # Extract collection name from self if available
                collection_name = args[0].collection.name if len(args) > 0 and hasattr(args[0], 'collection') else 'unknown'

                # Retrieve the MongoDB query from the function arguments
                query = next((arg for arg in args if isinstance(arg, dict)), {})
                if not query:
                    query = next((value for value in kwargs.values() if isinstance(value, dict)), {})

                duration = (time.time() - start_time) * 1000
               
                log_entry = {
                    'operation': operation,
                    'collection': collection_name,
                    'duration_ms': duration,
                    'request_id': request_id,
                    'timestamp': current_utc_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    'query': json.dumps({k: v for k, v in query.items() if k not in ['_id']}) if query else "{}",
                }
                file_logger.info(f"Database Operation: {json.dumps(log_entry)}")
                return result
            except Exception as e:
                file_logger.error(
                    "Error in database operation",
                    exc_info=True,
                    extra={'operation': operation, 'request_id': request_id, 'message_content': str(e), 'ctx': 'ERROR'}
                )
                raise

        return wrapper
    return decorator