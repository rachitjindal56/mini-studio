from app.middleware.logger.logging import file_logger
from utility.utils import current_utc_time


import functools
import json
import time


def log_database_operation(operation: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
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
                    'timestamp': current_utc_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    'query': json.dumps(query) if query else '{}',
                }
                file_logger.info(f'Database Operation: {json.dumps(log_entry)}', extra={'ctx': 'DB_OPERATION'})
                return result
            except Exception as e:
                file_logger.error(
                    'Error in database operation',
                    exc_info=True,
                    extra={'operation': operation, 'message_content': str(e), 'ctx': 'ERROR'}
                )
                raise

        return wrapper
    return decorator