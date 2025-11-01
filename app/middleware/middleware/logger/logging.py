import os
import time
import uuid
import logging
import json
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.middleware.logger.RequestContextManager import RequestContextManager
from app.middleware.logger.error_logger import ErrorLogger

from utility.utils import current_utc_time

log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

file_logger = logging.getLogger("request_file_logger")
file_logger.setLevel(logging.INFO)

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "ts": current_utc_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            "lv": record.levelname,
            "request_id": RequestContextManager.get_request_id(),
            "hash_key": getattr(record, 'hash_key', 'no-hash-key'),
            "sIp": getattr(record, 'sIp', 'unknown'),
            "fl": record.filename,
            "fn": record.funcName,
            "ln": record.lineno,
            "message_content": getattr(record, 'message_content', record.getMessage()),
            "ctx": getattr(record, 'ctx', '')
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

class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, request_response_logger: RequestResponseLogger):
        super().__init__(app)
        self.request_response_logger = request_response_logger
        self.error_logger = ErrorLogger()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request_id and get hash_key
        request_id = str(uuid.uuid4())
        hash_key = request.headers.get('X-Hash-Key', 'no-hash-key')

        RequestContextManager.set_request_id(request_id)

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
