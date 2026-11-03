import argparse
import re
import shlex
import sys
from pathlib import Path

SECRET_NAME = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|PASSWD|AUTH|DSN|CREDENTIAL", re.I)


def read_secrets(path):
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        tokens = shlex.split(line, comments=True)
        if tokens and tokens[0] == "export":
            tokens = tokens[1:]
        if len(tokens) != 1 or "=" not in tokens[0]:
            continue
        name, value = tokens[0].split("=", 1)
        if value and SECRET_NAME.search(name):
            values.append(value)
    return values


def check_rule(path: Path, secrets=()) -> list[str]:
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
    if any(value in text for value in secrets):
        problems.append("найдено значение из указанного файла секретов")
    return problems


def main():
    parser = argparse.ArgumentParser(description="Проверка формата правил и известных секретов")
    parser.add_argument("target", type=Path)
    parser.add_argument("--secrets-file", type=Path)
    args = parser.parse_args()
    target = args.target.expanduser()
    rules = [target] if target.is_file() else sorted(target.glob("*.mdc"))
    if not rules:
        parser.error("Не найдены файлы правил")
    secrets = read_secrets(args.secrets_file.expanduser()) if args.secrets_file else []
    failed = False
    for rule in rules:
        problems = check_rule(rule, secrets)
        failed = failed or bool(problems)
        print(("FAIL " if problems else "ok ") + rule.name + (": " + "; ".join(problems) if problems else ""))
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
