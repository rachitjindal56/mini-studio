import logging
from utility.utils import current_utc_time
from typing import Dict
import json

class ErrorLogger:
    def __init__(self):
        self.logger = logging.getLogger('error')

    def log_error(self, error: Exception, request_id: str, additional_info: Dict = {}):
        log_entry = {
            'timestamp': current_utc_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            'request_id': request_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'additional_info': additional_info
        }
        self.logger.error(f"Error Occurred: {json.dumps(log_entry)}")
