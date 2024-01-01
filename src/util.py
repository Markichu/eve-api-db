import asyncpg
import requests
import grequests

from typing import Generator

ESI_BASE_URL = "https://esi.evetech.net/latest"
CONCURRENT_REQUESTS = 16


async def connect_to_db() -> asyncpg.connection.Connection:
    conn = await asyncpg.connect(host="localhost", database="eve", user="postgres", password="password")
    return conn


async def esi_call(
    method_url: str, params: dict = None, headers: dict = None
) -> Generator[requests.Response, None, None]:
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
