# Подключение авто-бэкапа изменяемых файлов (для ИИ-агентов)

Этот проект требует, чтобы любой ИИ-агент (Claude Code и др.) перед изменением
файла сохранял его текущую версию в `.backups/files/` с версионностью
(см. правило в [CLAUDE.md](../CLAUDE.md) «Правила для всех ИИ»).

Сам скрипт — [`scripts/backup_hook.py`](../scripts/backup_hook.py) — **уже в
репозитории** (общий для команды). А вот **hook, который его вызывает, лежит в
`.claude/settings.json`, который намеренно gitignored** (локальные настройки ИИ).
Поэтому каждый участник подключает hook у себя **один раз** вручную.

> Нужен только Python 3 на PATH — он и так требуется для бэкенда, так что
> дополнительно ставить ничего не нужно.

---

## Шаг 1. Открыть свой `.claude/settings.json`

Файл в корне проекта: `<проект>/.claude/settings.json`.
Если его нет — создайте с содержимым `{ "hooks": {} }`.

## Шаг 2. Добавить hook в `hooks.PreToolUse`

Вставьте объект ниже в массив `hooks.PreToolUse`. **Если массив уже есть с
другими hook'ами — добавьте объект к ним, не затирая существующие.**

### Linux / macOS / Windows с Git Bash (рекомендуется)

Claude Code по умолчанию выполняет команды через bash (на Windows — через Git
Bash, если он установлен). Команда пробует `python3`, затем `python`:

```json
{
  "matcher": "Edit|Write|MultiEdit|NotebookEdit",
  "hooks": [
    {
      "type": "command",
      "command": "python3 \"$CLAUDE_PROJECT_DIR/scripts/backup_hook.py\" 2>/dev/null || python \"$CLAUDE_PROJECT_DIR/scripts/backup_hook.py\" 2>/dev/null || true",
      "statusMessage": "Бэкап изменяемого файла"
    }
  ]
}
```

### Windows без Git Bash (PowerShell)

Если Git Bash не установлен, Claude Code на Windows выполняет команду через
PowerShell. Тогда нужен PowerShell-вариант (другой синтаксис переменной и
путей) — явно задаём `"shell": "powershell"`:

```json
{
  "matcher": "Edit|Write|MultiEdit|NotebookEdit",
  "hooks": [
    {
      "type": "command",
      "shell": "powershell",
      "command": "python \"$env:CLAUDE_PROJECT_DIR\\scripts\\backup_hook.py\" 2>$null; exit 0",
      "statusMessage": "Бэкап изменяемого файла"
    }
  ]
}
```

> Не уверены, есть ли Git Bash? Откройте терминал и выполните `bash --version`.
> Если команда найдена — используйте первый (bash) вариант, он проще и
> переносимее. Если нет — PowerShell-вариант.

### Полный пример `.claude/settings.json` (если файл пустой)

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/scripts/backup_hook.py\" 2>/dev/null || python \"$CLAUDE_PROJECT_DIR/scripts/backup_hook.py\" 2>/dev/null || true",
            "statusMessage": "Бэкап изменяемого файла"
          }
        ]
      }
    ]
  }
}
```

## Шаг 3. Применить настройку

`.claude/settings.json` подхватывается при старте Claude Code и при открытии
меню `/hooks`. После правки файла:

- откройте `/hooks` в Claude Code (перечитает конфиг), **или**
- перезапустите Claude Code.

## Шаг 4. Проверить, что работает

Попросите Claude изменить любой файл проекта (или измените сами через Claude),
затем проверьте, что появилась версия в `.backups/files/`:

```bash
# Linux / macOS / Git Bash
ls -R .backups/files
```

```powershell
# Windows PowerShell
Get-ChildItem -Recurse .backups\files
```

Также можно проверить скрипт напрямую (без Claude):

```bash
# bash
echo '{"tool_input":{"file_path":"'"$PWD"'/CLAUDE.md"}}' | python3 scripts/backup_hook.py
```

```powershell
# PowerShell
'{"tool_input":{"file_path":"' + (Get-Location).Path.Replace('\','/') + '/CLAUDE.md"}}' | python scripts\backup_hook.py
```

Должна появиться копия `CLAUDE.md` в `.backups/files/CLAUDE.md/<таймстамп>.md`.

---

## Как это устроено

- **Скрипт** `scripts/backup_hook.py` (в git) читает JSON события из stdin,
  берёт `tool_input.file_path`, и копирует текущую версию файла в
  `.backups/files/<относительный путь>/<UTC-таймстамп><ext>`.
- Корень проекта вычисляется относительно расположения скрипта — **без
  абсолютных путей**.
- Бэкапятся только файлы **внутри проекта**; сама папка `.backups/` исключена
  (без рекурсии). Файлы больше 25 МБ пропускаются.
- Hook никогда не блокирует операцию: при любой ошибке завершается с кодом 0.
- В git **не попадают** сами бэкапы — `.gitignore` содержит `.backups/files/`.

## Частые вопросы

**«Python не найден» при срабатывании hook.**
Убедитесь, что `python` (или `python3`) доступен в PATH той оболочки, через
которую Claude Code запускает hooks. На Windows проще всего — установить Python
с python.org с галочкой «Add Python to PATH».

**Hook не срабатывает.**
Проверьте, что объект добавлен именно в `hooks.PreToolUse`, что JSON валиден
(один сломанный символ отключает весь файл настроек), и что вы перечитали конфиг
через `/hooks` или перезапуск.

**Можно ли коммитить свой `.claude/settings.json`?**
Нет — `.claude/` в `.gitignore` (личные настройки ИИ-агента). Поэтому подключение
hook — индивидуальный одноразовый шаг по этой инструкции.
