"""Reuse existing Ro-DOU services; only create a dedicated test database.

Credentials are read into memory from the existing local PostgreSQL container.
They are never written to files or printed. Tests only own their isolated records.
"""

import argparse
import json
import os
import subprocess
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-container", default="ro-dou-postgres-1")
    parser.add_argument("--postgres-port", type=int, default=5432)
    parser.add_argument("--test-database", default="ro_dou_ner_test")
    parser.add_argument("--opensearch-url", default="http://127.0.0.1:9200")
    parser.add_argument("--with-model", action="store_true")
    args = parser.parse_args()
    if "test" not in args.test_database.lower():
        parser.error("database name must contain test")
    try:
        info = json.loads(subprocess.check_output(["docker", "inspect", args.postgres_container]))[
            0
        ]
        variables = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
        credentials = {
            "host": "127.0.0.1",
            "port": args.postgres_port,
            "user": variables["POSTGRES_USER"],
            "password": variables["POSTGRES_PASSWORD"],
        }
        with psycopg.connect(dbname="postgres", autocommit=True, **credentials) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (args.test_database,)
            ).fetchone()
            if not exists:
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(args.test_database))
                )
        env = os.environ.copy()
        env["PGPASSWORD"] = credentials["password"]
        env["RO_DOU_NER_TEST_POSTGRES_DSN"] = make_conninfo(
            dbname=args.test_database,
            **{key: value for key, value in credentials.items() if key != "password"},
        )
        env["RO_DOU_NER_TEST_OPENSEARCH_URL"] = args.opensearch_url
        command = ["uv", "run", "--locked"]
        if args.with_model:
            command += ["--extra", "gliner"]
            env["RO_DOU_NER_TEST_GLINER"] = "1"
        command += ["pytest", "-q", "--cov=ro_dou_ner", "--cov-fail-under=90"]
        return subprocess.call(command, env=env)
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
