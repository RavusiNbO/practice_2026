import fastmcp
import psycopg
import logging
import sys
import httpx
from rag import search
import time
    
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(name)s ----- %(message)s")
loki_handler = logging.StreamHandler(sys.stdout)
loki_handler.setLevel(logging.INFO)
loki_handler.setFormatter(formatter)
logger.addHandler(loki_handler)
mcp = fastmcp.FastMCP("Databases")

DATABASE_DSN = (
    "dbname=satellites user=llm_reader password=llm_password "
    "host=postgres port=5432"
)
LOKI_QUERY_RANGE_URL = "http://loki:3100/loki/api/v1/query_range"


def escape_logql(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_logql(
    service: str | None,
    satellite: str | None,
    level: str | None,
    contains: str | None,
) -> str:
    labels = [
        f'job="{escape_logql(service)}"'
        if service
        else 'job=~".+"'
    ]

    if satellite:
        labels.append(f'satellite="{escape_logql(satellite)}"')

    if level:
        labels.append(f'level="{escape_logql(level)}"')

    query = "{" + ",".join(labels) + "}"

    if contains:
        query += f' |= "{escape_logql(contains)}"'

    return query


async def query_loki(
    query: str,
    start: int,
    end: int,
    limit: int,
) -> list[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            LOKI_QUERY_RANGE_URL,
            params={
                "query": query,
                "start": start,
                "end": end,
                "limit": limit,
                "direction": "backward",
            },
            timeout=5,
        )
        response.raise_for_status()

    result = []

    for stream in response.json()["data"]["result"]:
        for timestamp, message in stream["values"]:
            result.append(
                {
                    "timestamp": timestamp,
                    "labels": stream["stream"],
                    "message": message,
                }
            )

    return result



## TOOLS #############################################

@mcp.tool
async def list_satellites(limit: int = 100) -> list[dict]:
    """
    Return a list of satellites.

    Args:
        limit: Maximum number of satellites to return.
    """
    async with await psycopg.AsyncConnection.connect(
        DATABASE_DSN,
        row_factory=psycopg.rows.dict_row,
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT *
                FROM satellites
                ORDER BY id
                LIMIT %s
                """,
                (limit,),
            )
            return await cur.fetchall()

@mcp.tool
async def list_telemetry(
    limit: int = 100,
) -> list[dict]:
    """
    Return latest telemetry records.

    Args:
        limit: Maximum number of records.
    """
    async with await psycopg.AsyncConnection.connect(
        DATABASE_DSN,
        row_factory=psycopg.rows.dict_row,
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT *
                FROM telemetry
                ORDER BY timestamp_utc DESC
                LIMIT %s
                """,
                (
                    limit,
                ),
            )
            return await cur.fetchall()

@mcp.tool
async def describe_table(table: str) -> dict:
    """
    Return schema information about a PostgreSQL table.

    Args:
        table: Table name.
    """

    async with await psycopg.AsyncConnection.connect(
        DATABASE_DSN,
        row_factory=psycopg.rows.dict_row,
    ) as conn:

        async with conn.cursor() as cur:

            await cur.execute(
                """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position;
                """,
                (table,),
            )
            columns = await cur.fetchall()

            if not columns:
                raise ValueError(f"Table '{table}' does not exist.")
    return {
        "table": table,
        "columns": columns,
    }

@mcp.tool
async def find_satellites(
    name: str | None = None,
    orbit_type: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """
    Search satellites by name, orbit type or status.
    """
    sql = """
    SELECT *
    FROM satellites
    WHERE
        (%s::text IS NULL OR name ILIKE '%%' || %s || '%%')
        AND (%s::text IS NULL OR orbit_type = %s)
        AND (%s::text IS NULL OR status = %s)
    ORDER BY id
    LIMIT %s
    """

    async with await psycopg.AsyncConnection.connect(
        DATABASE_DSN,
        row_factory=psycopg.rows.dict_row,
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                sql,
                (
                    name, name,
                    orbit_type, orbit_type,
                    status, status,
                    limit,
                ),
            )
            return await cur.fetchall()

@mcp.tool
async def find_telemetry(
    satellite_id: int | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Search telemetry records.
    """

    sql = """
    SELECT *
    FROM telemetry
    WHERE
        (%s::integer IS NULL OR satellite_id = %s)
        AND (%s::timestamp IS NULL OR timestamp_utc >= %s::timestamp)
        AND (%s::timestamp IS NULL OR timestamp_utc <= %s::timestamp)
    ORDER BY timestamp_utc DESC
    LIMIT %s
    """

    async with await psycopg.AsyncConnection.connect(
        DATABASE_DSN,
        row_factory=psycopg.rows.dict_row,
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                sql,
                (
                    satellite_id,
                    satellite_id,
                    from_time,
                    from_time,
                    to_time,
                    to_time,
                    limit,
                ),
            )
            return await cur.fetchall()


@mcp.tool
async def search_logs(
    service: str | None = None,
    satellite: str | None = None,
    level: str | None = None,
    contains: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Search logs by job, satellite, level and message from the last 24 hours.
    """
    end = time.time_ns()
    start = end - 24 * 60 * 60 * 1_000_000_000
    query = build_logql(service, satellite, level, contains)

    return await query_loki(query, start, end, limit)


@mcp.tool
async def get_logs_last_minutes(
    minutes: int,
    service: str | None = None,
    satellite: str | None = None,
    level: str | None = None,
    contains: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Return logs from the last N minutes.

    Args:
        minutes: Time window in minutes.
        service: Job name (label "job").
        satellite: Satellite name (label "satellite").
        level: Log level (e.g. INFO, WARN, ERROR).
        contains: Message substring.
        limit: Maximum number of returned log lines.
    """

    end = time.time_ns()
    start = end - minutes * 60 * 1_000_000_000
    query = build_logql(service, satellite, level, contains)
    result = await query_loki(query, start, end, limit)

    logger.info("Loki query: %s", query)

    return result


@mcp.tool
async def search_documents(
    query: str,
    limit: int = 5,
) -> list[dict]:
    """
    Semantic search in indexed PDF documents.

    Args:
        query: Search query.
        limit: Maximum number of returned chunks.
    """
    return search(query, limit)
        
if __name__ == "__main__":
    mcp.run()
