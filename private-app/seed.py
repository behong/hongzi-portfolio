"""Seed one private post from a JSON document on stdin.

Expected JSON: {slug, title, summary, body_html, created_at}.
The post body is supplied at seed time only and is never stored in
this repository; it lands in the private_posts table in PostgreSQL.
"""
import json
import sys
import uuid

import pg8000

from app import connect, init_db


def main():
    doc = json.load(sys.stdin)
    for key in ("slug", "title", "summary", "body_html", "created_at"):
        if not doc.get(key):
            raise SystemExit(f"missing field: {key}")
    init_db()
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM private_posts WHERE slug=%s", (doc["slug"],))
        row = cur.fetchone()
        if row:
            cur.execute(
                """UPDATE private_posts
                   SET title=%s, summary=%s, body_html=%s, created_at=%s
                   WHERE slug=%s""",
                (doc["title"], doc["summary"], doc["body_html"],
                 doc["created_at"], doc["slug"]),
            )
            action = "updated"
        else:
            cur.execute(
                """INSERT INTO private_posts(id, slug, title, summary, body_html, created_at)
                   VALUES(%s, %s, %s, %s, %s, %s)""",
                (uuid.uuid4().hex, doc["slug"], doc["title"], doc["summary"],
                 doc["body_html"], doc["created_at"]),
            )
            action = "inserted"
        conn.commit()
        cur.execute("SELECT slug, length(body_html) FROM private_posts WHERE slug=%s",
                    (doc["slug"],))
        slug, size = cur.fetchone()
        print(f"{action}: {slug} (body_html {size} chars)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
