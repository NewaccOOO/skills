import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CHUNK_CHARS = 24000
EXTENSIONS = (".jsonl", ".jsonl.zst", ".json", ".txt", ".md")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def default_sources():
    home = Path.home()
    codex = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude"))
    return [
        ("codex", codex / "sessions"),
        ("codex", codex / "archived_sessions"),
        ("claude", claude / "projects"),
        ("cursor", home / ".cursor" / "projects"),
    ]


def read_text(path):
    if path.name.endswith(".zst"):
        executable = shutil.which("zstd")
        if not executable:
            raise ValueError("Для чтения .zst нужен zstd; источник не прочитан")
        result = subprocess.run([executable, "-dc", str(path)], capture_output=True)
        if result.returncode:
            raise ValueError("Не удалось распаковать .zst; источник не прочитан")
        return result.stdout.decode("utf-8")
    return path.read_bytes().decode("utf-8")


def source_files(location, errors):
    if location.is_file():
        return [location]
    files = []
    visited = set()
    for directory, folders, names in os.walk(
        location, followlinks=True,
        onerror=lambda error: errors.append({"path": str(error.filename), "error": type(error).__name__}),
    ):
        resolved = Path(directory).resolve()
        if resolved in visited:
            folders[:] = []
            continue
        visited.add(resolved)
        files.extend(Path(directory) / name for name in names)
    return sorted(files)


def collect(out, sources, scope):
    os.umask(0o077)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("Каталог результата должен быть новым или пустым")
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    out.chmod(0o700)
    chunks_dir = out / "chunks"
    chunks_dir.mkdir(mode=0o700)
    manifest = {"version": 2, "scope": scope, "sources": [], "locations": [], "errors": []}
    seen = set()
    for agent, location in sources:
        location = location.expanduser().resolve()
        status = {"agent": agent, "path": str(location), "exists": location.exists(), "unsupported": []}
        manifest["locations"].append(status)
        if not location.exists():
            manifest["errors"].append({"path": str(location), "error": "Указанный источник не существует"})
            continue
        candidates = source_files(location, manifest["errors"])
        for path in candidates:
            if not path.is_file():
                continue
            if not path.name.endswith(EXTENSIONS):
                if path.suffix in {".db", ".sqlite", ".sqlite3", ".vscdb"} or path == location:
                    status["unsupported"].append(str(path))
                continue
            if agent == "cursor" and location.is_dir() and "agent-transcripts" not in path.parts:
                continue
            if agent == "claude" and location.is_dir() and not path.name.endswith(".jsonl"):
                continue
            path = path.resolve()
            if path in seen:
                continue
            seen.add(path)
            try:
                text = read_text(path)
                source_id = digest((agent + ":" + str(path)).encode())
                source = {"id": source_id, "agent": agent, "path": str(path), "sha256": digest(text.encode()),
                          "chars": len(text), "chunks": [], "parse_errors": []}
                if path.name.endswith((".jsonl", ".jsonl.zst")):
                    for number, line in enumerate(text.splitlines(), 1):
                        if line.strip():
                            try:
                                json.loads(line)
                            except json.JSONDecodeError:
                                source["parse_errors"].append(number)
                elif path.suffix == ".json":
                    try:
                        json.loads(text)
                    except json.JSONDecodeError:
                        source["parse_errors"].append(1)
                for index, start in enumerate(range(0, max(1, len(text)), CHUNK_CHARS), 1):
                    part = text[start:start + CHUNK_CHARS]
                    name = f"{source_id}-{index:05d}.txt"
                    target = chunks_dir / name
                    target.write_bytes(part.encode("utf-8"))
                    target.chmod(0o600)
                    source["chunks"].append({"id": name, "path": f"chunks/{name}", "sha256": digest(part.encode()),
                                             "start": start, "end": start + len(part)})
                manifest["sources"].append(source)
            except (OSError, UnicodeError, ValueError) as error:
                manifest["errors"].append({"path": str(path), "error": type(error).__name__})
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Полная выгрузка истории агентов без обрезки и пересказа")
    parser.add_argument("out_dir", type=Path)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="общий рабочий процесс")
    scope.add_argument("--root", type=Path, help="проект; отбор по смыслу после чтения, без порога доли путей")
    parser.add_argument("--source", action="append", default=[], metavar="AGENT=PATH", help="источники вместо стандартных; повторяемый")
    args = parser.parse_args()
    sources = []
    for value in args.source:
        agent, separator, path = value.partition("=")
        if not separator or not agent or not path:
            parser.error("Источник задаётся как AGENT=PATH")
        sources.append((agent, Path(path)))
    if not sources:
        sources = [(agent, path) for agent, path in default_sources() if path.exists()]
    if not sources:
        parser.error("Стандартная история не найдена; найди хранилище агента и передай --source")
    try:
        manifest = collect(args.out_dir.expanduser().resolve(), sources, str(args.root.resolve()) if args.root else "all")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    unsupported = sum(len(location["unsupported"]) for location in manifest["locations"])
    print(f"Источников: {len(manifest['sources'])}; частей: {sum(len(s['chunks']) for s in manifest['sources'])}; "
          f"ошибок: {len(manifest['errors'])}; неподдерживаемых хранилищ: {unsupported}")
    return int(bool(manifest["errors"] or unsupported or any(s["parse_errors"] for s in manifest["sources"])))


if __name__ == "__main__":
    sys.exit(main())
