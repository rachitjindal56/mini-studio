import uuid
from functools import wraps
from typing import Any, Callable, TypeVar, ParamSpec, Coroutine
from app.middleware.logger.logging import file_logger

from utility.utils import current_utc_time


T = TypeVar("T")
P = ParamSpec("P")

def log_database_query(func: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, Coroutine[Any, Any, T]]:
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        # Extract collection name from the first argument (self) if available
        collection_name = args[0].__class__.__name__ if args else "Unknown"
        
        # Get function name as operation type
        operation = func.__name__
        
        # Log query start
        start_time = current_utc_time()
        query_id = uuid.uuid4()
        
        file_logger.info(
            f"DB Query Start | query_id: {query_id} | Collection: {collection_name} | "
            f"Operation: {operation}"
        )

        try:
            # Execute the database operation
            result = await func(*args, **kwargs)
            
            # Calculate execution time in milliseconds
            query_time = (current_utc_time() - start_time).total_seconds() * 1000 
            
            # Log successful query completion
            file_logger.info(
                f"DB Query Complete | query_id: {query_id} | Collection: {collection_name} | "
                f"Operation: {operation} | query_time_ms: {query_time:.2f}"
            )
            
            return result
            
        except Exception as e:
            # Log query error
            file_logger.error(
                f"DB Query Error | query_id: {query_id} | Collection: {collection_name} | "
                f"Operation: {operation} | Error: {str(e)}"
            )
            raise

    return wrapper
