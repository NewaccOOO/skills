import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_rules import SECRET_PATTERNS

PARSER_VERSION = 2
PROJECTS_DIR = Path.home() / ".cursor" / "projects"
AI_TEXT_LIMIT_CHARS = 1500
GROUP_LIMIT_CHARS = 150_000
ROOT_PATH_SHARE = 0.5
CONTEXT_TAGS = {
    "attached_files": "файлы",
    "code_selection": "выделенный код",
    "terminal_selection": "вывод терминала",
    "image_files": "картинки",
    "uploaded_documents": "документы",
}
ABORT_ERRORS = ("User aborted", "interrupted")
ACTIVITY_ITEMS_LIMIT = 15
FIRST_REQUEST_CHARS = 120
DETAIL_LABELS = ("команды", "скиллы", "MCP", "субагенты")
COMMAND_SEPARATORS = re.compile(r"&&|\|\||[;|\n]")
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?.*?^\s*\1\s*$", re.S | re.M)
COMMAND_NAME = re.compile(r"[a-z][a-z0-9_.+-]*")
SKIPPED_COMMANDS = {"cd", "do", "done", "then", "else", "fi", "for", "while", "if", "echo", "printf", "sleep"}
MCP_WRITE_TOOL = re.compile(
    r"^(?!(get|list|search|query|read|find|check|fetch)[_-]).*"
    r"(^|[_-])(create|update|edit|add|append|post|send|reply|comment|transition|assign|move|delete|set)([_-]|$)"
)
MCP_ARGS_LIMIT_CHARS = 1500
MCP_WRITES_PER_SEGMENT = 3


def scrub(text: str) -> str:
    for pattern in SECRET_PATTERNS.values():
        text = re.sub(pattern, "[секрет]", text)
    return text


def slugify(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-")


def belongs_to_root(project_slug: str, raw: str, root: str) -> bool:
    root_slug = slugify(root)
    if project_slug == root_slug:
        return True
    text = raw.replace("\\\\", "/")
    home = Path.home().as_posix() + "/"
    root_mentions = text.count(root + "/") + text.count(root + '"')
    home_mentions = max(text.count(home), root_mentions)
    if not home_mentions:
        return project_slug.startswith(root_slug + "-")
    return root_mentions / home_mentions >= ROOT_PATH_SHARE


def user_turn(text: str) -> str:
    queries = re.findall(r"<user_query>\s*(.*?)\s*</user_query>", text, re.S)
    if not queries:
        return ""
    context = re.sub(r"<user_query>.*?</user_query>", "", text, flags=re.S)
    marks = [label for tag, label in CONTEXT_TAGS.items() if f"<{tag}" in context]
    timestamp = re.search(r"<timestamp>(.*?)</timestamp>", text)
    head = f"[{timestamp.group(1)}] USER" if timestamp else "USER"
    if marks:
        head += " (+" + ", +".join(marks) + ")"
    return head + ":\n" + "\n\n".join(queries)


def command_heads(command: str) -> list[str]:
    heads = []
    for segment in COMMAND_SEPARATORS.split(HEREDOC.sub("", command)):
        words = segment.split()
        while words and "=" in words[0]:
            words.pop(0)
        head = words[0].rsplit("/", 1)[-1] if words else ""
        if not COMMAND_NAME.fullmatch(head) or head in SKIPPED_COMMANDS:
            continue
        if len(words) > 1 and re.fullmatch(r"[a-z][a-z-]*", words[1]):
            head += " " + words[1]
        heads.append(head)
    return heads


@dataclass
class Segment:
    ai_texts: list[str] = field(default_factory=list)
    tools: Counter = field(default_factory=Counter)
    details: dict[str, list[str]] = field(default_factory=lambda: {label: [] for label in DETAIL_LABELS})
    mcp_writes: list[str] = field(default_factory=list)

    def add_detail(self, label: str, items: list[str]):
        for item in items:
            if item not in self.details[label]:
                self.details[label].append(item)

    def add_tool(self, name: str, tool_input):
        self.tools[name] += 1
        if not isinstance(tool_input, dict):
            return
        if isinstance(tool_input.get("command"), str):
            self.add_detail("команды", command_heads(tool_input["command"]))
        if str(tool_input.get("path", "")).endswith("SKILL.md"):
            self.add_detail("скиллы", [Path(tool_input["path"]).parent.name])
        server = str(tool_input.get("server") or tool_input.get("namespace") or "").removeprefix("user-")
        tool_name = str(tool_input.get("toolName") or "")
        if server and server != "cursor" and tool_name:
            self.add_detail("MCP", [f"{server}.{tool_name}"])
            if MCP_WRITE_TOOL.search(tool_name):
                arguments = json.dumps(tool_input.get("arguments"), ensure_ascii=False)[:MCP_ARGS_LIMIT_CHARS]
                self.mcp_writes.append(f"MCP-WRITE {server}.{tool_name}: {arguments}")
        if name in ("Task", "Subagent") and tool_input.get("description"):
            self.add_detail("субагенты", [str(tool_input["description"])])

    def render(self) -> list[str]:
        lines = []
        if self.tools:
            counts = ", ".join(f"{name}×{count}" for name, count in self.tools.most_common())
            details = [
                f"{label}: {', '.join(items[:ACTIVITY_ITEMS_LIMIT])}" for label, items in self.details.items() if items
            ]
            lines.append(f"…({sum(self.tools.values())} tool calls: " + "; ".join([counts, *details]) + ")")
        lines += self.mcp_writes[-MCP_WRITES_PER_SEGMENT:]
        for ai_text in self.ai_texts[-2:]:
            cut = ai_text if len(ai_text) <= AI_TEXT_LIMIT_CHARS else ai_text[:AI_TEXT_LIMIT_CHARS] + " […]"
            lines.append("AI: " + cut)
        return lines


def render_dialog(events: list[dict]) -> tuple[list[str], int]:
    turns = []
    segment = Segment()
    user_count = 0
    for event in events:
        if event.get("type") == "turn_ended":
            error = str(event.get("error") or "")
            if event.get("status") == "aborted" or any(mark in error for mark in ABORT_ERRORS):
                turns.append("\n".join(segment.render() + ["USER-ABORT: пользователь прервал ход агента"]))
                segment = Segment()
            continue
        parts = event.get("message", {}).get("content", [])
        if event.get("role") == "user":
            text = user_turn("".join(part.get("text", "") for part in parts))
            if not text:
                continue
            turns.append("\n".join(segment.render() + [text]))
            segment = Segment()
            user_count += 1
            continue
        for part in parts:
            if part.get("type") == "tool_use":
                segment.add_tool(part.get("name", "?"), part.get("input"))
            elif part.get("type") == "text" and part.get("text", "").strip() not in ("", "[REDACTED]"):
                segment.ai_texts.append(part["text"].strip())
    tail = segment.render()
    if tail:
        turns.append("\n".join(tail))
    return turns, user_count


def first_request(events: list[dict]) -> str:
    for event in events:
        if event.get("role") != "user":
            continue
        text = "".join(part.get("text", "") for part in event.get("message", {}).get("content", []))
        match = re.search(r"<user_query>\s*(.*?)\s*</user_query>", text, re.S)
        if match:
            return " ".join(match.group(1).split())[:FIRST_REQUEST_CHARS]
    return ""


def parse_timestamp(text: str):
    try:
        return datetime.strptime(text.split(" (")[0], "%A, %b %d, %Y, %I:%M %p")
    except ValueError:
        return None


def split_parts(header: str, turns: list[str]) -> list[str]:
    parts = []
    current = header
    for turn in turns:
        if len(current) + len(turn) > GROUP_LIMIT_CHARS and current != header:
            parts.append(current)
            current = header + "(продолжение)\n\n"
        current += turn + "\n\n"
    parts.append(current)
    return parts


def main():
    parser = argparse.ArgumentParser(description="Собирает диалоги Cursor по папке проекта или все сразу")
    parser.add_argument("out_dir")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--root", help="папка проекта: её чаты, чаты подпапок и окон с несколькими папками")
    scope.add_argument("--all", action="store_true", help="все чаты Cursor на этой машине")
    parser.add_argument("--state", help="state.json прошлого запуска: чаты без изменений пропускаются")
    args = parser.parse_args()
    state_path = Path(args.state).expanduser() if args.state else None
    previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path and state_path.exists() else {}
    seen = previous.get("transcripts", {}) if previous.get("parser") == PARSER_VERSION else {}
    fingerprints = {}
    unchanged = 0
    root = "все папки" if args.all else Path(args.root).expanduser().resolve().as_posix()
    out_dir = Path(args.out_dir)
    dialog_dir = out_dir / "dialog"
    dialog_dir.mkdir(parents=True, exist_ok=True)

    sessions = []
    for transcript in sorted(PROJECTS_DIR.glob("*/agent-transcripts/*/*.jsonl")):
        project_slug = transcript.relative_to(PROJECTS_DIR).parts[0]
        raw = transcript.read_text(encoding="utf-8", errors="replace")
        if not args.all and not belongs_to_root(project_slug, raw, root):
            continue
        transcript_key = transcript.relative_to(PROJECTS_DIR).as_posix()
        stat = transcript.stat()
        fingerprints[transcript_key] = [stat.st_size, int(stat.st_mtime)]
        if seen.get(transcript_key) == fingerprints[transcript_key]:
            unchanged += 1
            continue
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        turns, user_count = render_dialog(events)
        if not user_count:
            continue
        session_id = transcript.stem
        stamps = re.findall(r"<timestamp>(.*?)</timestamp>", raw)
        times = [moment for moment in map(parse_timestamp, stamps) if moment]
        start = min(times) if times else datetime.fromtimestamp(stat.st_mtime)
        start_text = start.strftime("%Y-%m-%d %H:%M") if times else start.strftime("%Y-%m-%d")
        duration = "длительность неизвестна"
        if len(times) > 1:
            duration = f"{int((max(times) - start).total_seconds() // 60)} мин"
        aborts = sum("USER-ABORT" in turn for turn in turns)
        request = scrub(first_request(events))
        header = (
            f"# {session_id} · {project_slug} · начало {start_text} · {duration}"
            f" · реплик: {user_count} · прерываний: {aborts}\n\n"
        )
        for index, text in enumerate(split_parts(header, [scrub(turn) for turn in turns]), 1):
            name = f"{start.strftime('%Y-%m-%d_%H%M')}_{session_id[:8]}_{index}.md"
            (dialog_dir / name).write_text(text, encoding="utf-8")
            sessions.append((name, len(text), project_slug, duration, user_count, aborts, request))

    sessions.sort()
    groups = []
    for name, size, *_ in sessions:
        if not groups or groups[-1][1] + size > GROUP_LIMIT_CHARS:
            groups.append([[], 0])
        groups[-1][0].append(name)
        groups[-1][1] += size

    state = {"parser": PARSER_VERSION, "transcripts": fingerprints}
    (out_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [
        f"Корень: {root}",
        f"Диалогов: {len(sessions)}",
        f"Пропущено, потому что не менялись с прошлого запуска: {unchanged}",
        "",
        "Папки:",
    ]
    folders = Counter(project for name, _, project, *_ in sessions if name.endswith("_1.md"))
    lines += [f"{count}\t{project}" for project, count in folders.most_common()]
    lines.append("")
    lines += [
        f"{name}\t{project}\t{duration}\tреплик {count}\tпрерываний {aborts}\t{request}"
        for name, _, project, duration, count, aborts, request in sessions
    ]
    lines.append("")
    for index, (names, size) in enumerate(groups, 1):
        lines.append(f"Группа {index} ({size // 1000}k символов): " + " ".join(names))
    summary = "\n".join(lines)
    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
