import re
import sys
from pathlib import Path

MAX_LINES = {".mdc": 50, ".md": 150}
SECRET_PATTERNS = {
    "логин и пароль в URL": r"://[^/\s:@]+:[^/\s@]+@",
    "JWT": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "Bearer или Basic токен": r"(?i)\b(bearer|basic)\s+[A-Za-z0-9+/=._-]{16,}",
    "значение секрета": r"(?i)(token|password|passwd|secret|api[_-]?key)['\"]?\s*[=:]\s*['\"]?[A-Za-z0-9+/=._-]{8,}",
    "токен с префиксом": r"\b[a-z]{2,6}[-_](?=[A-Za-z0-9_-]*[A-Z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{20,}",
    "длинная случайная строка": r"(?<![A-Za-z0-9+])(?=[A-Za-z0-9+]*\d)(?=[A-Za-z0-9+]*[A-Za-z])[A-Za-z0-9+]{32,}\b",
}


def check_rule(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems = []
    frontmatter = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if path.suffix == ".mdc" and not frontmatter:
        problems.append("нет frontmatter между строками ---")
    elif path.suffix == ".mdc":
        if not re.search(r"^description: *\S", frontmatter.group(1), re.M):
            problems.append("пустой description")
        if not re.search(r"^alwaysApply: *(true|false)$", frontmatter.group(1), re.M):
            problems.append("alwaysApply не true и не false")
    max_lines = MAX_LINES.get(path.suffix, MAX_LINES[".md"])
    if len(text.splitlines()) > max_lines:
        problems.append(f"длиннее {max_lines} строк")
    for label, pattern in SECRET_PATTERNS.items():
        if re.search(pattern, text):
            problems.append(f"похоже на секрет: {label}")
    return problems


def main():
    target = Path(sys.argv[1]).expanduser()
    rules = [target] if target.is_file() else sorted(target.glob("*.mdc"))
    if not rules:
        print(f"FAIL нет .mdc в {target}")
        sys.exit(1)
    failed = False
    for rule in rules:
        problems = check_rule(rule)
        failed = failed or bool(problems)
        print(f"{'FAIL' if problems else 'ok'} {rule.name}" + (": " + "; ".join(problems) if problems else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
