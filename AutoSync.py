"""Keep the working files in sync with GitHub without writing to .git."""
import argparse
import base64
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import time

REPOSITORY = "behong/hongzi-portfolio"
ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / ".tools" / "autosync"
PROTECTED = {".git", ".secrets", ".tools", ".env"}


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def target_path(root, name):
    parts = PurePosixPath(name).parts
    if not parts or "\\" in name or ":" in name or any(p in {".", ".."} for p in parts):
        raise ValueError("Invalid repository path: " + name)
    if parts[0].casefold() in PROTECTED or parts[0].casefold().startswith(".env."):
        raise ValueError("Protected repository path: " + name)
    target = root.joinpath(*parts)
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise ValueError("Repository path escapes workspace: " + name)
    return target


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".autosync-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class GitHub:
    def api(self, path):
        result = subprocess.run(
            ["gh", "api", "repos/" + REPOSITORY + "/" + path],
            capture_output=True, encoding="utf-8", timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode:
            raise RuntimeError("GitHub request failed: " + result.stderr.strip())
        return json.loads(result.stdout)

    def head(self):
        return self.api("git/ref/heads/main")["object"]["sha"]

    def tree(self, commit):
        result = self.api("git/trees/" + commit + "?recursive=1")
        if result.get("truncated"):
            raise RuntimeError("Incomplete GitHub tree; update cancelled")
        files = {}
        for entry in result["tree"]:
            if entry["type"] != "blob":
                continue
            if entry["mode"] not in {"100644", "100755"}:
                raise RuntimeError("Unsupported file mode: " + entry["path"])
            files[entry["path"]] = entry["sha"]
        return files

    def download(self, sha):
        result = self.api("git/blobs/" + sha)
        if result["encoding"] != "base64":
            raise RuntimeError("Unsupported blob encoding")
        content = base64.b64decode(result["content"])
        if blob_sha(content) != sha:
            raise RuntimeError("GitHub file hash mismatch")
        return content


def sync(root, runtime, github):
    state_path = runtime / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"commit": None, "files": {}}
    commit = github.head()
    if state["commit"] == commit:
        return []
    remote = github.tree(commit)
    previous = state["files"]
    paths = {name: target_path(root, name) for name in remote.keys() | previous.keys()}
    changes = []
    conflicts = []
    inspected = {}
    # Validate all destinations and local edits before changing any files.
    for name, target in paths.items():
        current = blob_sha(target.read_bytes()) if target.is_file() else None
        if target.exists() and not target.is_file():
            conflicts.append(name)
            continue
        inspected[name] = current
        wanted, old = remote.get(name), previous.get(name)
        if current == wanted:
            continue
        if current != old:
            conflicts.append(name)
        else:
            changes.append((name, wanted))
    if conflicts:
        raise RuntimeError("Local changes preserved; sync paused for: " + ", ".join(sorted(conflicts)))
    # Fetch and verify every new blob before touching the working files.
    downloaded = {name: github.download(sha) for name, sha in changes if sha}
    for name, _ in changes:
        target = paths[name]
        current = blob_sha(target.read_bytes()) if target.is_file() else None
        if current != inspected[name]:
            raise RuntimeError("Local file changed during download; sync cancelled: " + name)
    for name, sha in changes:
        target = paths[name]
        if target.exists():
            backup = runtime / "backups" / commit / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copy2(target, backup)
        if sha:
            atomic_write(target, downloaded[name])
        else:
            target.unlink()
        logging.info("%s %s", "Updated" if sha else "Deleted", name)
    # On first start, only an identical checkout or absent files can be adopted.
    atomic_write(state_path, json.dumps({"commit": commit, "files": remote}, indent=2).encode())
    logging.info("Synced %s (%d files changed)", commit, len(changes))
    if any(name in {"Caddyfile", "cloudflared.yml", "docker-compose.yml"} for name, _ in changes):
        logging.warning("Deployment configuration changed. Run Start-Portfolio.ps1 to apply it.")
    return [name for name, _ in changes]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    if args.interval < 30:
        parser.error("interval must be at least 30 seconds")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    handlers = [RotatingFileHandler(RUNTIME / "watcher.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    lock = (RUNTIME / "watcher.lock").open("a+b")
    lock.seek(0)
    lock.write(b"0")
    lock.flush()
    lock.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        logging.info("Another watcher is already running")
        return
    atomic_write(RUNTIME / "process.json", json.dumps({"pid": os.getpid(), "script": str(Path(__file__).resolve())}).encode())
    logging.info("Watching %s main every %d seconds", REPOSITORY, args.interval)
    try:
        while True:
            try:
                sync(ROOT, RUNTIME, GitHub())
                atomic_write(RUNTIME / "heartbeat.json", json.dumps({"checked_at": time.time(), "ok": True}).encode())
            except Exception:
                logging.exception("Sync failed; will retry")
                atomic_write(RUNTIME / "heartbeat.json", json.dumps({"checked_at": time.time(), "ok": False}).encode())
                if args.once:
                    return 1
            if args.once:
                break
            time.sleep(args.interval)
    finally:
        (RUNTIME / "process.json").unlink(missing_ok=True)
        lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
