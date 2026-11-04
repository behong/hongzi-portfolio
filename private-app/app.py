"""Private posts space for hongzi.us (/private).

Minimal standalone service:
- Login form -> session cookie -> post list / post body.
- Accounts are reused from the trade-journal (suik) users table in the
  local PostgreSQL database; password verification is byte-for-byte the
  same PBKDF2 scheme as trade-journal/server.py (sha256, 600k rounds,
  "salt_hex:digest_hex"). Only owner accounts (is_owner=1) may enter.
- Post bodies live only in PostgreSQL (private_posts). Nothing about the
  posts is stored in this repository.
"""
import hashlib
import hmac
import html
import os
import re
import secrets
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pg8000

BASE = "/private"
SESSION_COOKIE = "private_session"
CSRF_COOKIE = "private_csrf"
SESSION_TTL = 30 * 86400
MAX_FAILS = 5
LOCK_SECONDS = 600

CSS = """
:root{color-scheme:light dark}
body{font-family:-apple-system,'Segoe UI','Malgun Gothic',sans-serif;margin:0;line-height:1.75}
.wrap{max-width:760px;margin:0 auto;padding:24px 18px 64px}
h1{font-size:1.55rem;line-height:1.4;margin:.2em 0 .4em}
h2{font-size:1.2rem;margin:1.6em 0 .5em}
.tag{color:#888;font-size:.85rem;margin:0}
.meta{color:#888;font-size:.85rem;margin:.2em 0 1em}
.summary{font-size:1.02rem}
article p{margin:.7em 0}
article li{margin:.35em 0}
.linkdesc{color:#888;font-size:.9rem}
.card{border:1px solid #8884;border-radius:12px;padding:16px 18px;margin:14px 0}
.card a{font-size:1.1rem;font-weight:600;text-decoration:none}
.card p{margin:.4em 0;color:#666}
input[type=email],input[type=password]{width:100%;box-sizing:border-box;padding:12px;border:1px solid #8886;border-radius:8px;font-size:1rem;margin:6px 0 14px}
button{padding:11px 22px;border:0;border-radius:8px;background:#2f6feb;color:#fff;font-size:1rem;cursor:pointer}
.err{color:#c0392b}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.topbar form{margin:0}
.topbar button{background:none;color:#888;padding:4px 8px;font-size:.9rem}
label{font-weight:600;font-size:.92rem}
"""


def pg_params():
    password = os.environ.get("JOURNAL_PG_PASSWORD")
    if not password:
        raise RuntimeError("JOURNAL_PG_PASSWORD is not set")
    return {
        "host": os.environ.get("JOURNAL_PG_HOST", "host.docker.internal"),
        "port": int(os.environ.get("JOURNAL_PG_PORT", "5432")),
        "database": os.environ.get("JOURNAL_PG_DB", "trade_journal"),
        "user": os.environ.get("JOURNAL_PG_USER", "suik_app"),
        "password": password,
    }


def connect():
    return pg8000.connect(**pg_params())


def init_db():
    ddl = [
        """CREATE TABLE IF NOT EXISTS private_posts (
               id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL,
               title TEXT NOT NULL, summary TEXT NOT NULL,
               body_html TEXT NOT NULL, created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS private_sessions (
               token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
               expires DOUBLE PRECISION NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS private_login_attempts (
               email TEXT PRIMARY KEY, fails INTEGER NOT NULL DEFAULT 0,
               locked_until DOUBLE PRECISION NOT NULL DEFAULT 0)""",
    ]
    last_error = None
    for _ in range(30):
        try:
            conn = connect()
            try:
                cur = conn.cursor()
                for stmt in ddl:
                    cur.execute(stmt)
                conn.commit()
            finally:
                conn.close()
            return
        except Exception as exc:  # PostgreSQL may still be starting
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"cannot initialise database: {last_error}")


# --- password verification: identical scheme to trade-journal/server.py ---

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 600000
    ).hex()
    return salt + ":" + digest


def password_matches(password, stored):
    return (
        isinstance(password, str)
        and len(password) <= 128
        and hmac.compare_digest(password_hash(password, stored.split(":")[0]), stored)
    )


def authenticate(email, password):
    """Return the user row dict for an owner account, else None."""
    email = email.strip().lower() if isinstance(email, str) else ""
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, password, is_owner FROM users WHERE email=%s", (email,))
        row = cur.fetchone()
    finally:
        conn.close()
    stored = row[1] if row else "00" * 16 + ":" + "00" * 32
    valid = password_matches(password, stored)
    if not row or not valid or int(row[2]) != 1:
        return None
    return {"id": row[0], "email": email}


# --- login throttling (mirrors suik: 5 failures -> 10 minute lock) ---

def login_locked(email):
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT locked_until FROM private_login_attempts WHERE email=%s", (email,)
        )
        row = cur.fetchone()
        return bool(row and row[0] > time.time())
    finally:
        conn.close()


def record_failure(email):
    now = time.time()
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT fails FROM private_login_attempts WHERE email=%s", (email,)
        )
        row = cur.fetchone()
        fails = (row[0] if row else 0) + 1
        locked_until = now + LOCK_SECONDS if fails >= MAX_FAILS else 0
        if fails >= MAX_FAILS:
            fails = 0
        cur.execute(
            """INSERT INTO private_login_attempts(email, fails, locked_until)
               VALUES(%s, %s, %s)
               ON CONFLICT(email) DO UPDATE
               SET fails=EXCLUDED.fails, locked_until=EXCLUDED.locked_until""",
            (email, fails, locked_until),
        )
        conn.commit()
    finally:
        conn.close()


def clear_failures(email):
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM private_login_attempts WHERE email=%s", (email,))
        conn.commit()
    finally:
        conn.close()


# --- sessions ---

def create_session(user_id):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM private_sessions WHERE expires<=%s", (time.time(),))
        cur.execute(
            "INSERT INTO private_sessions(token_hash, user_id, expires) VALUES(%s,%s,%s)",
            (token_hash, user_id, time.time() + SESSION_TTL),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def session_user(token):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id FROM private_sessions WHERE token_hash=%s AND expires>%s",
            (token_hash, time.time()),
        )
        row = cur.fetchone()
        if not row:
            return None
        cur.execute(
            "SELECT id, email, name, is_owner FROM users WHERE id=%s", (row[0],)
        )
        user = cur.fetchone()
        if not user or int(user[3]) != 1:
            return None
        return {"id": user[0], "email": user[1], "name": user[2]}
    finally:
        conn.close()


def delete_session(token):
    if not token:
        return
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM private_sessions WHERE token_hash=%s", (token_hash,))
        conn.commit()
    finally:
        conn.close()


def list_posts():
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT slug, title, summary, created_at FROM private_posts "
            "ORDER BY created_at DESC, title"
        )
        return [
            {"slug": r[0], "title": r[1], "summary": r[2], "created_at": r[3]}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def get_post(slug):
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT slug, title, body_html, created_at FROM private_posts WHERE slug=%s",
            (slug,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"slug": row[0], "title": row[1], "body_html": row[2], "created_at": row[3]}
    finally:
        conn.close()


def page(title, inner):
    return (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta name='robots' content='noindex, nofollow'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body><main class='wrap'>{inner}</main></body></html>"
    )


def login_page(csrf, error=None):
    err = f"<p class='err'>{html.escape(error)}</p>" if error else ""
    return page(
        "비공개 글 — 로그인",
        "<h1>비공개 글</h1>"
        "<p>본인 전용 공간입니다. 매매일지(suik)와 같은 계정으로 로그인하세요.</p>"
        + err
        + f"""<form method="post" action="{BASE}/login">
        <input type="hidden" name="csrf" value="{html.escape(csrf, quote=True)}">
        <label for="email">이메일</label>
        <input type="email" id="email" name="email" required autocomplete="username">
        <label for="password">비밀번호</label>
        <input type="password" id="password" name="password" required autocomplete="current-password">
        <button type="submit">로그인</button>
        </form>""",
    )


def list_page(user, posts):
    cards = []
    for post in posts:
        date = post["created_at"].replace("-", ". ")
        cards.append(
            f"<div class='card'><a href='{BASE}/post/{html.escape(post['slug'], quote=True)}'>"
            f"{html.escape(post['title'])}</a>"
            f"<p>{html.escape(post['summary'])}</p><p>{html.escape(date)}</p></div>"
        )
    if not cards:
        cards.append("<p>아직 등록된 글이 없습니다.</p>")
    inner = (
        "<div class='topbar'><span>비공개 글</span>"
        f"<form method='post' action='{BASE}/logout'>"
        "<button type='submit'>로그아웃</button></form></div>"
        + "".join(cards)
    )
    return page("비공개 글", inner)


def post_page(user, post):
    inner = (
        "<div class='topbar'><a href='" + BASE + "/'>← 목록</a>"
        f"<form method='post' action='{BASE}/logout'>"
        "<button type='submit'>로그아웃</button></form></div>"
        f"<article><h1>{html.escape(post['title'])}</h1>"
        + post["body_html"]
        + "</article>"
    )
    return page(post["title"], inner)


class Handler(BaseHTTPRequestHandler):
    server_version = "PrivatePosts/1.0"

    # -- helpers ---------------------------------------------------------
    def _send(self, status, body, content_type="text/html; charset=utf-8", headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (headers or []):
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location, headers=None):
        self._send(303, "", headers=[("Location", location)] + (headers or []))

    def _cookies(self):
        jar = cookies.SimpleCookie()
        raw = self.headers.get("Cookie")
        if raw:
            try:
                jar.load(raw)
            except cookies.CookieError:
                pass
        return {key: morsel.value for key, morsel in jar.items()}

    def _user(self):
        return session_user(self._cookies().get(SESSION_COOKIE))

    def _form(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(min(length, 65536)).decode("utf-8")
        parsed = parse_qs(raw)
        return {key: values[0] for key, values in parsed.items()}

    # -- routing ---------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path == BASE + "/health":
            return self._send(200, "ok", "text/plain; charset=utf-8")
        if path == BASE:
            return self._redirect(BASE + "/")
        if path == BASE + "/login":
            if self._user():
                return self._redirect(BASE + "/")
            csrf = secrets.token_urlsafe(24)
            cookie = (
                f"{CSRF_COOKIE}={csrf}; Path={BASE}; HttpOnly; Secure; "
                "SameSite=Lax; Max-Age=3600"
            )
            return self._send(200, login_page(csrf), headers=[("Set-Cookie", cookie)])
        if path == BASE + "/logout":
            return self._redirect(BASE + "/")
        user = self._user()
        if not user:
            return self._redirect(BASE + "/login")
        if path == BASE + "/":
            return self._send(200, list_page(user, list_posts()))
        match = re.fullmatch(re.escape(BASE) + r"/post/([a-z0-9-]+)", path)
        if match:
            post = get_post(match.group(1))
            if post:
                return self._send(200, post_page(user, post))
        return self._send(404, page("없음", "<h1>찾을 수 없습니다</h1>"))

    def do_POST(self):
        path = urlparse(self.path).path
        if path == BASE + "/login":
            form = self._form()
            jar = self._cookies()
            csrf_cookie = jar.get(CSRF_COOKIE, "")
            if not csrf_cookie or not hmac.compare_digest(
                csrf_cookie, form.get("csrf", "")
            ):
                return self._send(403, page("오류", "<h1>요청이 만료되었습니다</h1><p><a href='" + BASE + "/login'>다시 로그인</a></p>"))
            email = (form.get("email") or "").strip().lower()
            password = form.get("password") or ""
            if login_locked(email):
                return self._send(
                    200,
                    login_page(
                        csrf_cookie,
                        "로그인 시도가 많아 잠시 잠겼습니다. 10분 후 다시 시도해 주세요.",
                    ),
                )
            user = authenticate(email, password)
            if not user:
                record_failure(email)
                return self._send(
                    200,
                    login_page(csrf_cookie, "이메일 또는 비밀번호가 올바르지 않습니다."),
                )
            clear_failures(email)
            token = create_session(user["id"])
            cookie = (
                f"{SESSION_COOKIE}={token}; Path={BASE}; HttpOnly; Secure; "
                f"SameSite=Lax; Max-Age={SESSION_TTL}"
            )
            return self._redirect(BASE + "/", headers=[("Set-Cookie", cookie)])
        if path == BASE + "/logout":
            delete_session(self._cookies().get(SESSION_COOKIE))
            cookie = (
                f"{SESSION_COOKIE}=; Path={BASE}; HttpOnly; Secure; "
                "SameSite=Lax; Max-Age=0"
            )
            return self._redirect(
                BASE + "/login", headers=[("Set-Cookie", cookie)]
            )
        return self._send(404, page("없음", "<h1>찾을 수 없습니다</h1>"))

    def log_message(self, fmt, *args):  # keep logs free of query strings
        super().log_message(fmt, *args)


def main():
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", 8766), Handler)
    print("private posts service listening on 8766", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
