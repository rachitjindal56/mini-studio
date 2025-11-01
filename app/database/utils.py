import httpx
import json
from typing import Optional, Dict, Any

async def make_api_call(
    method: str, 
    endpoint: str, 
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str,Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = 60
) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method,
                url=endpoint,
                headers=headers,
                **({"content": json.dumps(payload)} if payload else {}),
                **({"params": params} if params else {})
            )
            response.raise_for_status()
            return response.json()

    except httpx.TimeoutException as e:
        raise TimeoutError(f"Request timed out: {str(e)}")

    except httpx.HTTPStatusError as e:
        raise

    except Exception as e:
        raise