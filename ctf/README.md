# CTF

Сторонние наборы скиллов для CTF и авторизованного пентеста. Собраны здесь как есть,
с сохранением исходных README и лицензий. Перед добавлением каждый набор был прочитан
на предмет опасного кода — итоги в разделе [Что проверено](#что-проверено).

## Наборы

| Набор | Что внутри | Скиллов | Источник | Лицензия |
|---|---|---|---|---|
| [`ctf-claude`](ctf-claude/) | recon, web, бинарная эксплуатация, privesc (Linux/Windows), docker escape, AD, ADCS, SQLi | 9 | [hatrickkkk/ctf-claude](https://github.com/hatrickkkk/ctf-claude) | не указана |
| [`hacking-skills`](hacking-skills/) | web (28), mobile (7), CI/CD (5), meta (3) — методики по OWASP WSTG/MASTG | 43 | [securityfortech/hacking-skills](https://github.com/securityfortech/hacking-skills) | не указана |
| [`claude-code-pentest`](claude-code-pentest/) | recon, attack-path, web-эксплуатация, API, cloud pivot, цепочки уязвимостей — 43 python-скрипта | 6 | [Orizon-eu/claude-code-pentest](https://github.com/Orizon-eu/claude-code-pentest) | MIT |

`ctf-claude` — самый прямой под CTF: скиллы разбиты по типовым категориям задач.
`hacking-skills` — чистые методички без кода, сильны по вебу. `claude-code-pentest` —
скрипты на весь цикл от разведки до отчёта.

## Установка локально

Наборы, где каждый скилл — это папка с `SKILL.md` (`ctf-claude`, `claude-code-pentest`),
копируются прямо в каталог скиллов Claude Code:

```bash
git clone https://github.com/NewaccOOO/skills.git
cp -R skills/ctf/ctf-claude/skills/* ~/.claude/skills/
cp -R skills/ctf/claude-code-pentest/{recon-dominator,attack-path-architect,webapp-exploit-hunter,api-breaker,cloud-pivot-finder,vuln-chain-composer} ~/.claude/skills/
```

`hacking-skills` устроен как плагин-маркетплейс (`.claude-plugin/marketplace.json`),
а не как набор отдельных папок. Его подключают маркетплейсом, а не копированием:

```bash
/plugin marketplace add securityfortech/hacking-skills
```

## Kali-MCP для ctf-claude

Сами по себе скиллы `ctf-claude` — это текст-инструкции. Чтобы Claude реально запускал
`nmap`, `gobuster` и прочие тулзы, нужен отдельный сторонний сервер
[mcp-kali-server](https://github.com/heverin/mcp-kali-server), прописанный в `~/.claude.json`.
Он даёт Claude выполнять произвольные команды на машине с Kali. Ставь его осознанно:
только в изолированном Kali (docker или VM), без доступа в рабочую сеть.

## Что проверено

Перед переносом каждый набор был склонирован и прочитан. Результаты:

- **Install-скрипты** (`ctf-claude/install.sh`, `install.ps1`) только копируют `SKILL.md`
  в `~/.claude/skills/`. Ни сети, ни удаления файлов, ни доступа к твоим данным.
- **Доступа к локальным секретам** (`~/.ssh`, `~/.aws`, `.env`, `.claude.json`, keychain)
  в скриптах нет.
- **Эксфильтрации на чужую инфру нет.** Строки вида `attacker.com/exfil`,
  `curl … | bash`, `169.254.169.254` — это примеры payload'ов и учебный текст внутри
  markdown, с плейсхолдерами (`ATTACKER`, `CALLBACK`, `<KALI_IP>`).
- **Сетевые вызовы** в python `claude-code-pentest` идут только к публичным recon-API
  (crt.sh, web.archive.org, hackertarget, поиск Google/GitHub) и запрашивают данные
  о цели, которую ты сам укажешь.

Проверялся код, а не репутация авторов. Репозитории молодые, поручиться за авторов нельзя.
Два набора без файла лицензии (`ctf-claude`, `hacking-skills`) — по умолчанию все права
у авторов; хранятся здесь как копии с указанием источника.

## Границы применения

Только авторизованное тестирование: CTF-соревнования, свои стенды, пентест с письменным
разрешением. Прогоняй тулзы строго по scope. На части CTF AI-ассист ограничен или запрещён
правилами — проверь регламент до старта.
