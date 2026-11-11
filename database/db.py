import os
import json
import psycopg
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


def _conn():
    return psycopg.connect(DATABASE_URL, autocommit=True)


def init():
    with _conn() as conn:
        conn.execute(
            """
            create table if not exists kv (
                key text primary key,
                value jsonb not null,
                updated_at timestamptz not null default now()
            )
            """
        )


def get(key, default=None):
    with _conn() as conn:
        row = conn.execute("select value from kv where key = %s", (key,)).fetchone()
    return row[0] if row else default


def put(key, value):
    with _conn() as conn:
        conn.execute(
            """
            insert into kv (key, value) values (%s, %s::jsonb)
            on conflict (key) do update set value = excluded.value, updated_at = now()
            """,
            (key, json.dumps(value)),
        )


def delete(key):
    with _conn() as conn:
        conn.execute("delete from kv where key = %s", (key,))