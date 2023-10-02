import asyncpg

async def connect_to_db() -> asyncpg.connection.Connection:
    conn = await asyncpg.connect(
        host="localhost",
        database="eve",
        user="postgres",
        password="password"
    )
    return conn