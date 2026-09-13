# CTF

Скиллы для CTF и авторизованного пентеста. Взяты из сторонних репозиториев, каждый
скилл прочитан на предмет опасного кода перед добавлением — итоги в разделе
[Что проверено](#что-проверено).

Раскладка: каждый скилл лежит как `ctf/<имя>/SKILL.md` (плюс `scripts/` и `references/`,
где они есть), поэтому ставится через `npx skills` по имени. Исключение — `hacking-skills`:
это плагин со своим графом и агентами, он лежит целиком в [`hacking-skills/`](hacking-skills/)
и ставится отдельно.

## Установка

Отдельные скиллы (15 штук из наборов ctf-claude и claude-code-pentest):

```bash
# один скилл по имени
npx skills add NewaccOOO/skills -a claude-code -g --skill ctf-recon

# все скиллы репозитория
npx skills add NewaccOOO/skills -a claude-code -g
```

`hacking-skills` — плагин, подключается маркетплейсом:

```bash
/plugin marketplace add securityfortech/hacking-skills
```

## Скиллы и источники

| Скилл | Источник | Лицензия |
|---|---|---|
| `ctf-recon`, `ctf-web`, `ctf-sqli`, `ctf-bof`, `ctf-ad`, `ctf-adcs`, `ctf-docker-escape`, `ctf-privesc-linux`, `ctf-privesc-windows` | [hatrickkkk/ctf-claude](https://github.com/hatrickkkk/ctf-claude) | не указана |
| `recon-dominator`, `webapp-exploit-hunter`, `api-breaker`, `attack-path-architect`, `cloud-pivot-finder`, `vuln-chain-composer` | [Orizon-eu/claude-code-pentest](https://github.com/Orizon-eu/claude-code-pentest) | MIT |
| `hacking-skills` (плагин, 43 скилла: web/mobile/CI-CD) | [securityfortech/hacking-skills](https://github.com/securityfortech/hacking-skills) | не указана |

Исходные README и файл MIT-лицензии сохранены в папках-источниках
[`ctf-claude/`](ctf-claude/) и [`claude-code-pentest/`](claude-code-pentest/).

`ctf-claude` — самый прямой под CTF, скиллы разбиты по типовым категориям задач.
Его описания-триггеры написаны на португальском, так что автоматически подхватываются
хуже — зови по имени. `claude-code-pentest` — python-скрипты на весь цикл от разведки
до отчёта. `hacking-skills` — методички без кода, сильны по вебу.

## Kali-MCP для ctf-claude

Сами скиллы `ctf-claude` — это текст-инструкции. Чтобы Claude реально запускал `nmap`,
`gobuster` и прочие тулзы, нужен отдельный сторонний сервер
[mcp-kali-server](https://github.com/heverin/mcp-kali-server), прописанный в `~/.claude.json`
(эти скиллы ссылаются на его тулзы в `allowed-tools`). Он даёт Claude выполнять
произвольные команды на машине с Kali. Ставь его осознанно: только в изолированном Kali
(docker или VM), без доступа в рабочую сеть.

## Что проверено

Перед переносом каждый набор был склонирован и прочитан. Результаты:

- **Install-скрипты** оригинального `ctf-claude` только копировали `SKILL.md` в каталог
  скиллов — ни сети, ни удаления файлов, ни доступа к данным. Здесь они уже не нужны
  (скиллы ставятся через `npx skills`) и удалены.
- **Доступа к локальным секретам** (`~/.ssh`, `~/.aws`, `.env`, `.claude.json`, keychain)
  в скриптах нет.
- **Эксфильтрации на чужую инфру нет.** Строки вида `attacker.com/exfil`, `curl … | bash`,
  `169.254.169.254` — это примеры payload'ов и учебный текст внутри markdown,
  с плейсхолдерами (`ATTACKER`, `CALLBACK`, `<KALI_IP>`).
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
