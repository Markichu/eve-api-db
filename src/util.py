import asyncpg
import requests
import grequests

from typing import AsyncGenerator, Any

ESI_BASE_URL = "https://esi.evetech.net/latest"
CONCURRENT_REQUESTS = None


async def connect_to_db() -> asyncpg.connection.Connection:
    conn = await asyncpg.connect(host="localhost", database="eve", user="postgres", password="password")
    return conn


async def esi_call(
    method_url: str, params: dict = None, headers: dict = None
) -> AsyncGenerator[requests.Response, None]:
    params = params or {}
    endpoint_url = ESI_BASE_URL + method_url

    yield (response := requests.get(endpoint_url, params=params, headers=headers, timeout=10))

    if not response.headers.get("X-Pages"):
        return

    pages = int(response.headers["X-Pages"])
    other_requests = (
        grequests.get(endpoint_url, params=params | {"page": i}, headers=headers) for i in range(2, pages + 1)
    )
    for response in grequests.imap(other_requests, size=CONCURRENT_REQUESTS):
        yield response


async def esi_call_itemwise(method_url: str, params: dict = None, headers: dict = None) -> AsyncGenerator[Any, None]:
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
        for item in response.json():
            yield item
            
async def gather_generator(generator):
    return [item async for item in generator]
