import argparse
import base64
import binascii
import collections
import json
import os
import pathlib
import re

PROJECTS = pathlib.Path.home() / ".claude" / "projects"
CLAUDE_JSON = pathlib.Path.home() / ".claude.json"
SYSTEM_REMINDER = re.compile(r"<(system-reminder|task-notification)>.*?</\1>", re.S)
GROUP_LIMIT = 250_000
PART_LIMIT = 400_000
CONFIG_MAX_BYTES = 1_000_000
TOOL_RESULT_SUFFIXES = {".txt", ".json", ".html", ".md", ".log", ".yaml", ".yml"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
             "dist", "build", ".deps", ".idea", ".tox", "site-packages", ".next", "coverage", "htmlcov"}
CONFIG_NAME = re.compile(r"^\.env|\.env$|^(docker-)?compose.*\.ya?ml$|\.(ini|cfg|conf|toml|properties|ya?ml|json|tfvars)$"
                         r"|^(settings|config).*\.py$|^\.(pgpass|npmrc|pypirc|netrc)$")

PATTERNS = {
    "dsn": r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb|rediss?|amqps?|clickhouse|mssql|sqlserver|oracle|cockroachdb|jdbc:[a-z]+)"
           r"(?:\+[a-z0-9_]+)?://[^\s'\"`<>]+",
    "db_kv": r"(?i)\b(?:host|hostaddr|server|data source)\s*=\s*[^\s;'\"]+[^\n'\"]{0,200}?\b(?:password|pwd)\s*=\s*[^\s;'\"]+",
    "db_cli": r"\b(?:PGPASSWORD=\S+\s+)?(?:psql|pg_dump|pg_restore|mysql|mysqldump|mongosh|redis-cli|clickhouse-client)\s+-[^\n|;&]{2,200}",
    "db_env": r"\b[A-Z0-9_]*(?:DATABASE|DB|PG|POSTGRES|MYSQL|MONGO|REDIS|CLICKHOUSE|RABBIT|AMQP)[A-Z0-9_]*\s*[=:]\s*['\"]?[^\s'\"`]{2,}",
    "url_creds": r"\bhttps?://[^/\s:@'\"]+:[^/\s@'\"]+@[^\s'\"`<>]+",
    "env_secret": r"\b[A-Z][A-Z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD|PASSWD|PWD|PASS|DSN|URI|AUTH|CREDENTIALS?|DATABASE_URL"
                  r"|CONN(?:ECTION)?_STRING)\b\s*[=:]\s*['\"]?[^\s'\"`]{4,}",
    "api_key": r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}|\bBBDC-[A-Za-z0-9+/=]{20,}|\bgh[pousr]_[A-Za-z0-9]{30,}|\bglpat-[A-Za-z0-9_-]{20,}"
               r"|\bxox[abp]-[A-Za-z0-9-]{20,}|\bAKIA[0-9A-Z]{16}|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "auth_header": r"(?i)\b(?:Bearer|Basic|Api-Token)\s+[A-Za-z0-9+/=_.-]{12,}",
    "config_secret": r"(?i)[\"']?\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret)"
                     r"[\"']?\s*[:=]\s*[\"']?([^\s\"',;}{()]{4,})",
    "ssh": r"\b[\w.-]+@(?:\d{1,3}\.){3}\d{1,3}\b(?:\s+\S{6,})?|\bssh\s+(?:-\S+\s+)*[\w.-]+@[\w.-]+(?:\s+\S{6,})?",
    "private_ip": r"\b(?:10|172|192)\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d{2,5})?\b",
    "device": r"(?i)\b(?:iPhone (?:SE|1\d)(?: Pro(?: Max)?| Plus| mini)?|Pixel[_ ]\w+|emulator-\d{4}|Medium_Phone\w*)\b",
    "user_cred": r"(?i)(?<!\w)(?:пароль|password|passwd|логин|login|пасскод|passcode|пин-?код|токен|token)\s*[:=\-–]?\s*['\"`]?[^\s'\"`,;]{3,60}",
    "uuid": r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    "high_entropy": r"(?<![\w+/=.-])[A-Za-z0-9+/=_.-]{20,}(?![\w+/=.-])",
    "value_keyword": r"(?i)(?<!\S)[^\s'\"`]{6,}\s+(?:вот\s+|это\s+)?(?:мой\s+|наш\s+)?(?:токен|пароль|ключ|креды|кред|token|password|api key)",
}
USER_ONLY = {"private_ip", "device", "user_cred", "uuid", "high_entropy", "value_keyword"}
COMPILED = {name: re.compile(rx) for name, rx in PATTERNS.items()}


def char_class(char):
    if char.islower():
        return "l"
    if char.isupper():
        return "u"
    if char.isdigit():
        return "d"
    return "o"


def looks_random(value):
    if value.startswith(("/", "~", "./", "toolu_", "http")) or "=" in value.rstrip("="):
        return False
    if re.search(r"[a-z]{6,}", value) and re.search(r"[/-]", value):
        return False
    classes = [char_class(c) for c in value]
    if not {"l", "u", "d"} <= set(classes):
        return False
    switches = sum(1 for a, b in zip(classes, classes[1:]) if a != b)
    return switches / len(value) >= 0.3


def has_signal(value):
    return bool(re.search(r"\d|[^\w.]", value))


FILTERS = {
    "high_entropy": lambda match: looks_random(match.group(0)),
    "config_secret": lambda match: has_signal(match.group(1)),
}


def session_cwd(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            if '"cwd"' not in raw:
                continue
            try:
                cwd = json.loads(raw).get("cwd")
            except json.JSONDecodeError:
                continue
            if cwd:
                return cwd
    return None


def records(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue


def result_text(block):
    result = block.get("content")
    if isinstance(result, list):
        result = " ".join(item.get("text", "") for item in result if isinstance(item, dict))
    return result or ""


def texts(record):
    kind = record.get("type")
    content = (record.get("message") or {}).get("content")
    if kind == "queue-operation" and record.get("content"):
        yield "U", SYSTEM_REMINDER.sub("", record["content"])
    if kind == "user" and not record.get("isMeta"):
        if isinstance(content, str):
            yield "U", SYSTEM_REMINDER.sub("", content)
            return
        for block in content or []:
            if block.get("type") == "text":
                yield "U", SYSTEM_REMINDER.sub("", block.get("text", ""))
            elif block.get("type") == "tool_result":
                yield "R", result_text(block)
    if kind == "assistant":
        for block in content or []:
            if block.get("type") == "text":
                yield "A", block.get("text", "")
            elif block.get("type") == "tool_use":
                yield "T", json.dumps(block.get("input", {}), ensure_ascii=False)


def tool_line(block):
    name = block.get("name", "")
    params = block.get("input") or {}
    if name == "Bash":
        return f"TOOL Bash: {params.get('description', '')} | {params.get('command', '')}"
    if name in ("Edit", "MultiEdit", "Write", "Read", "NotebookEdit"):
        return f"TOOL {name}: {params.get('file_path', params.get('notebook_path', ''))}"
    if name in ("Agent", "Task"):
        return f"TOOL {name}: {params.get('description', '')} :: {params.get('prompt', '')}"
    return f"TOOL {name}: {json.dumps(params, ensure_ascii=False)}"


def condense(path):
    lines, title = [], None
    for record in records(path):
        kind = record.get("type")
        if kind == "custom-title":
            title = record.get("customTitle") or record.get("title")
        if kind not in ("user", "assistant") or record.get("isSidechain"):
            continue
        stamp = (record.get("timestamp") or "")[:16]
        content = (record.get("message") or {}).get("content")
        if kind == "user":
            if record.get("isMeta"):
                continue
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
            for block in blocks:
                if block.get("type") == "text":
                    text = SYSTEM_REMINDER.sub("", block.get("text", "")).strip()
                    if text:
                        lines.append(f"\n[{stamp}] USER: {text}")
                elif block.get("type") == "tool_result":
                    result = result_text(block)
                    if "user doesn't want" in result or "the user said" in result.lower():
                        lines.append(f"[{stamp}] USER-REJECT: {result.strip()}")
            continue
        for block in content or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                lines.append(f"[{stamp}] AI: {block['text'].strip()}")
            elif block.get("type") == "tool_use":
                lines.append(f"[{stamp}] {tool_line(block)}")
    return (f"TITLE: {title}\n" if title else "") + "\n".join(lines)


def dialog(condensed):
    out, ai_lines, tools = [], [], 0
    for part in re.split(r"(?m)^(?=\[\d{4}-)", condensed):
        match = re.match(r"\[[^\]]*\] (USER-REJECT|USER|AI|TOOL)", part)
        if not match:
            if part.startswith("TITLE"):
                out.append(part.strip())
            continue
        kind = match.group(1)
        if kind == "AI":
            ai_lines.append(part.strip())
        elif kind == "TOOL":
            tools += 1
        else:
            if ai_lines or tools:
                out.append(f"  …({tools} tool calls)")
                out.extend(ai_lines[-2:])
            ai_lines, tools = [], 0
            out.append("\n" + part.strip())
    if ai_lines or tools:
        out.append(f"  …({tools} tool calls)")
        out.extend(ai_lines[-2:])
    return "\n".join(out)


def user_keys(text):
    return [m.group(1)[:200] for m in re.finditer(r"\n\[[^\]]*\] USER: (.*?)(?=\n\[|\Z)", text, re.S)]


def cut_fork(text, primary_keys):
    keys = user_keys(text)
    common = 0
    while common < min(len(keys), len(primary_keys)) and keys[common] == primary_keys[common]:
        common += 1
    if common == 0:
        return text, 0
    starts = [m.start() for m in re.finditer(r"\n\[[^\]]*\] USER: ", text)]
    tail = text[starts[common]:] if common < len(starts) else ""
    return f"FORK: первые {common} реплик пользователя совпадают с основной сессией и вырезаны.\n{tail}", common


def split_parts(path, text):
    if len(text.encode("utf-8")) <= PART_LIMIT:
        return [path]
    starts = [m.start() for m in re.finditer(r"\n\[[^\]]*\] USER: ", text)] + [len(text)]
    parts, begin, index = [], 0, 1
    for cut in starts:
        if len(text[begin:cut].encode("utf-8")) >= PART_LIMIT // 2 or cut == len(text):
            part = path.with_name(f"{path.stem}.part{index}.md")
            part.write_text(text[begin:cut], encoding="utf-8")
            parts.append(part)
            begin, index = cut, index + 1
    path.unlink()
    return parts


def encode(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def decode_basic(encoded):
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    return decoded if ":" in decoded and decoded.isprintable() else None


def scan(stats, text, source, label):
    for name, rx in COMPILED.items():
        if name in USER_ONLY and source != "U":
            continue
        check = FILTERS.get(name)
        for match in rx.finditer(text):
            if check and not check(match):
                continue
            start = max(0, match.start() - 100)
            context = text[start:match.end() + 100]
            found = [(name, match.group(0).strip())]
            if name == "auth_header" and match.group(0).lower().startswith("basic "):
                decoded = decode_basic(match.group(0)[6:].strip())
                if decoded:
                    found.append(("basic_decoded", decoded))
            for key in found:
                item = stats[key]
                item["U" if source == "U" else "other"].add(label)
                if source == "U" or not item["ctx"]:
                    item["ctx"] = context


def config_files(root):
    for directory, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            path = pathlib.Path(directory) / name
            if CONFIG_NAME.search(name) and not path.is_symlink() and path.stat().st_size <= CONFIG_MAX_BYTES:
                yield path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("out")
    parser.add_argument("--skip", default="")
    args = parser.parse_args()
    root = str(pathlib.Path(args.root).resolve())
    out = pathlib.Path(args.out)

    own_dirs = {encode(root)}
    own_dirs |= {encode(p) for p in pathlib.Path(root).glob("*") if p.is_dir()}
    own_dirs |= {encode(p) for p in pathlib.Path(root).glob("*/*") if p.is_dir()}

    sessions = []
    for path in sorted(PROJECTS.glob("*/*.jsonl")):
        if path.stem == args.skip:
            continue
        cwd = session_cwd(path) or ""
        if path.parent.name in own_dirs or cwd == root or cwd.startswith(root + "/"):
            sessions.append((path, cwd))

    memory_dirs = sorted({str(path.parent / "memory") for path, _ in sessions if (path.parent / "memory").is_dir()}
                         | {str(d / "memory") for d in PROJECTS.iterdir()
                            if (d / "memory").is_dir() and d.name in own_dirs})

    stats = collections.defaultdict(lambda: {"U": set(), "other": set(), "ctx": ""})
    counts = collections.Counter()
    rows = []
    for path, cwd in sessions:
        sid = path.stem[:8]
        condensed = condense(path)
        target = out / "condensed" / path.parent.name / f"{path.stem}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(condensed, encoding="utf-8")
        stamps = re.findall(r"\[(\d{4}-\d\d-\d\d)T", condensed)
        rows.append({"path": path, "cwd": cwd, "condensed": condensed,
                     "dates": f"{stamps[0]}..{stamps[-1]}" if stamps else "",
                     "users": len(user_keys(condensed)), "interrupts": condensed.count("Request interrupted"),
                     "title": condensed.splitlines()[0][7:60] if condensed.startswith("TITLE") else ""})
        for record in records(path):
            for source, text in texts(record):
                scan(stats, text, "S" if record.get("isSidechain") else source, sid)
        session_dir = path.parent / path.stem
        for transcript in session_dir.glob("subagents/**/*.jsonl"):
            counts["subagent transcripts"] += 1
            for record in records(transcript):
                for _, text in texts(record):
                    scan(stats, text, "S", sid)
        for saved in session_dir.glob("tool-results/**/*"):
            if saved.suffix in TOOL_RESULT_SUFFIXES:
                counts["saved tool results"] += 1
                scan(stats, saved.read_text(encoding="utf-8", errors="replace"), "R", sid)

    for path in config_files(root):
        counts["config files"] += 1
        scan(stats, path.read_text(encoding="utf-8", errors="replace"), "F", f"file:{path.relative_to(root)}")
    if CLAUDE_JSON.exists():
        projects = json.loads(CLAUDE_JSON.read_text(encoding="utf-8")).get("projects", {})
        for key, entry in projects.items():
            if key == root or key.startswith(root + "/"):
                counts["claude.json projects"] += 1
                scan(stats, json.dumps(entry, ensure_ascii=False), "F", f"claude.json:{key}")

    by_first = collections.defaultdict(list)
    for row in rows:
        keys = user_keys(row["condensed"])
        by_first[keys[0] if keys else row["path"].stem].append(row)
    family_of = {}
    for family in by_first.values():
        family.sort(key=lambda r: -r["users"])
        family_of.update({row["path"].stem[:8]: family[0]["path"].stem[:8] for row in family})
        primary_keys = user_keys(dialog(family[0]["condensed"]))
        for row in family:
            text = dialog(row["condensed"])
            row["fork_of"], row["cut"] = "", 0
            if row is not family[0]:
                text, row["cut"] = cut_fork(text, primary_keys)
                row["fork_of"] = family[0]["path"].stem[:8] if row["cut"] else ""
            target = out / "dialog" / row["path"].parent.name / f"{row['path'].stem}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            row["parts"] = split_parts(target, text)

    with open(out / "facts.tsv", "w", encoding="utf-8") as handle:
        handle.write("kind\tuser_sessions\tother_sources\tvalue\tsources\tcontext\n")
        for item in stats.values():
            item["typed"] = len({family_of.get(sid, sid) for sid in item["U"]})
        ordered = sorted(stats.items(), key=lambda kv: (-kv[1]["typed"], -len(kv[1]["other"]), kv[0][0]))
        for (name, value), item in ordered:
            sources = ",".join(sorted(item["U"] | item["other"]))
            value = re.sub(r"\s", lambda m: "\\n" if m.group(0) == "\n" else " ", value)
            context = re.sub(r"\s", " ", item["ctx"][:300])
            handle.write(f"{name}\t{item['typed']}\t{len(item['other'])}\t{value}\t{sources}\t{context}\n")

    files = [(p, p.stat().st_size) for row in rows for p in row["parts"] if p.stat().st_size > 60]
    files.sort(key=lambda f: -f[1])
    groups = []
    for path, size in files:
        for group in groups:
            if group["size"] + size <= GROUP_LIMIT:
                group["files"].append(path)
                group["size"] += size
                break
        else:
            groups.append({"files": [path], "size": size})

    typed = sum(1 for item in stats.values() if item["U"])
    lines = [f"root: {root}", f"sessions: {len(rows)}",
             "scanned: " + ", ".join(f"{name} {value}" for name, value in sorted(counts.items())),
             f"facts: {len(stats)} values, typed by user: {typed}", "", "memory dirs:", *memory_dirs, "", "sessions:"]
    for row in sorted(rows, key=lambda r: r["dates"]):
        fork = f" fork_of={row['fork_of']} cut={row['cut']}" if row["fork_of"] else ""
        lines.append(f"{row['path'].stem[:8]} {row['dates']} users={row['users']} intr={row['interrupts']}"
                     f" dir={row['path'].parent.name} cwd={row['cwd']}{fork} | {row['title']}")
    lines += ["", f"groups for subagents (dialog files, ≤{GROUP_LIMIT // 1000}K each):"]
    for number, group in enumerate(groups, 1):
        lines.append(f"G{number} {group['size'] // 1000}K: " + " ".join(str(p.relative_to(out / 'dialog')) for p in group["files"]))
    (out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
