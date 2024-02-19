import httpx
import asyncio
import asyncpg
import logging

from typing import AsyncGenerator, Any
from requests import Response

LOGGER = logging.getLogger("uvicorn.access")
ESI_BASE_URL = "https://esi.evetech.net/latest"
CONCURRENT_REQUESTS = 50
HTTPX_LIMITS = httpx.Limits(max_keepalive_connections=CONCURRENT_REQUESTS, max_connections=CONCURRENT_REQUESTS)
HTTPX_TIMEOUT = httpx.Timeout(None)
GLOBAL_SESSION = httpx.AsyncClient(timeout=HTTPX_TIMEOUT, limits=HTTPX_LIMITS)


async def connect_to_db() -> asyncpg.connection.Connection:
    conn = await asyncpg.connect(host="localhost", database="eve", user="postgres", password="password")
    return conn


async def esi_call(
    method_url: str, params: dict = None, headers: dict = None
) -> AsyncGenerator[Response, None]:
    params = params or {}
    endpoint_url = ESI_BASE_URL + method_url

    # make initial request
    yield (response := await GLOBAL_SESSION.get(endpoint_url, params=params, headers=headers, timeout=10))

    # see if we have headers to make more requests
    if not response.headers.get("X-Pages"):
        return
    
    # make additional requests to get all the data
    pages = int(response.headers["X-Pages"])
    other_requests = (
        GLOBAL_SESSION.get(endpoint_url, params=params | {"page": i}, headers=headers) for i in range(2, pages + 1)
    )
    for response in await asyncio.gather(*other_requests):
        yield response


async def esi_call_itemwise(method_url: str, params: dict = None, headers: dict = None) -> AsyncGenerator[Any, None]:
    try:
        async for response in esi_call(method_url, params=params, headers=headers):
            # yield response data
            yield {
                "is_headers": True,
                "expires": response.headers.get("expires", 0),
                "last-modified": response.headers.get("last-modified", 0),
                "x-esi-error-limit-remain": response.headers.get("x-esi-error-limit-remain", 0),
                "x-esi-error-limit-reset": response.headers.get("x-esi-error-limit-reset", 0),
                "x-pages": response.headers.get("x-pages", 0),
            }
            if response.status_code != 200:
                raise Exception(f"ESI call failed with status code {response.status_code}")
            if "application/json" not in response.headers.get("Content-Type", ""):
                raise Exception(f"ESI call failed with non-JSON response: {response.text}")
            if not response.text:
                continue
            for item in response.json():
                yield item
    except Exception as e:
        LOGGER.error(f"Exception in esi_call_itemwise: {e}")
        yield None
            
async def gather_generator(generator):
    return [item async for item in generator]
