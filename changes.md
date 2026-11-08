# Дайджест змін

## 2026-11-08 — аудит MLT-5 виявив і виправив відбір позадіапазонних піків

- Прямо відтворено PR3 TC-01…12 на DSP-коді: усі числові/негативні критерії пройшли. Додатково перевірено PR4 довгий 800 kHz/800000-frame сигнал; 440 Hz і amplitude 1.0 відновились. Одноразовий час — спостереження, не benchmark.
- Виявлено, що `min_frequency_hz` застосовувався після відносного amplitude threshold і SciPy `distance`; сильні піки нижче вибраного діапазону могли повністю прибрати слабші валідні піки. Порядок виправлено в `src/signal_proc/processing.py`: reference maximum рахується в діапазоні, а фізичну відстань застосовано після його фільтрації.
- Два до/після сценарії пройшли: 100 Hz поза діапазоном більше не приховує 1000 Hz/0.02; 500 Hz більше не витісняє 505 Hz/0.5 при межі 503 Hz. `py_compile` також пройшов. У checkout немає формальної `tests/` директорії; перевірки виконано inline, файлів тестів не додавали.
- Live Jira Sprint 1/assignee лишається невідомим через недоступний Jira MCP і відсутній Docker. Докази й обмеження — у `jira.md`, `status.md`, `testing.md`.

## 2026-11-08 — розпочато аудит Sprint 1 і числової коректності MLT-5

- Зафіксовано межу доказів Jira: у цьому запуску недоступні live issue/sprint поля, бо Atlassian MCP має стан `Unsupported`, локально відсутній Docker, а доступного Jira issue-query tool немає. Персональний список задач Sprint 1 невідомий; старі screenshots лишаються лише історичними.
- Перший огляд checkout підтвердив реалізацію лише `src/audio_contracts/` та `src/signal_proc/`; каталогу `tests/` немає. Точна перевірка очікувань PR3/PR4 і контрольовані DSP-експерименти тривають; поки жоден числовий висновок не позначено як доведений.
- Підстава: поточний `git status`, список вихідних файлів, `python3 .codex/codex-project.py mcp list`, відсутній executable `docker`, історичні критерії в `testing.md`.

## 2026-11-08 — налаштовано рольовий Jira workflow Codex

- Додано локальні Codex ролі для Jira fetch/sprint planning, implementer, reviewer, bug reporter і status updater; конфігурація та інструкції лишаються у Git-ignored `.codex/`.
- Workflow вимагає live Jira дані, залежності й acceptance criteria; незалежний reviewer gate перед Done; перехід тільки через доступну Jira workflow transition і перевірку status/Resolution після запису.
- Зафіксовано bug-report шаблон на основі Atlassian guidance: чіткий заголовок, кроки відтворення, environment, expected/actual, вплив і evidence; reporter перевіряє дублікати та не вигадує priority/severity/root cause.
- Локальний MCP write scope звужений до MLT та потрібних Jira tools. У цій роботі Jira не змінювали; Docker відсутній, тому handshake і статусний workflow не перевірені.
- Підстава: локальні `.codex/` role/workflow files; [Atlassian Bug Report Template](https://www.atlassian.com/software/jira/templates/bug-report), [Jira Cloud issue transitions API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/), [Atlassian Resolution guidance](https://support.atlassian.com/jira-cloud-administration/docs/what-is-a-resolution-in-jira/), [Codex custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents).

## 2026-11-08 — відновлено контекст, контракт і роботу KB

### Теоретична база

- За чотирма наданими DOCX і вбудованими Jira screenshots систематизовано мету системи, епіки/задачі MLT-1…MLT-5, план тестування, 12 кейсів, 18 checklist-пунктів і 4 potential bugs. Подробиці та точні очікування — у `backlog.md` і `testing.md`.
- Знімки статусів, планові строки, тест-кейси та bug reports позначено як історичні/непідтверджені. Jira наживо не перевіряли; результати запуску тестів у звітах не зафіксовані.
- Описано межу MLT-4 → MLT-5 через `AudioPacket`/`AudioReadError`, правила версії, помилок одного файла, масивів і IPC. Рекомендовано, щоб worker читав і обробляв один WAV локально, а parent передавав лише легкий file job. Дизайн worker-а ще не реалізований.

### Код і верифікація

- MLT-5 переміщено в `src/signal_proc/`; додано `src/audio_contracts/`; `process_signal` приймає `AudioPacket`. Цей код і README запушені в `origin/main` комітом `a2ef008`.
- Editable package build і компіляція Python-файлів пройшли. Тести не запускались. Фактичні API й DSP обмеження описані в `system.md`; джерело істини — поточний код.
- Залишено handover щодо незакоміченого локального видалення `tools/build_mlt5_protocol.py`. Його не відновлювали й не комітили; версія в `origin/main` ще описує попередній API, і її подальшу долю треба вирішити окремо.

### Топологія Git і постійне ведення KB

- Початковий локальний KB checkout як окремий вкладений Git-репозиторій не відповідав задуму користувача про одну базу на orphan-гілці того самого репозиторію. Кінцева схема — linked worktree кореневого репозиторію на гілці `kb-only`, зі спільним `origin` і окремою orphan-історією без спільного предка з `main`.
- У `kb-only` залишено лише документи KB; `knowledge-base/` і локальний `AGENTS.md` ігноруються в `main`. Публікувати знання дозволено лише в `origin/kb-only`; merge/cherry-pick у `main` заборонені.
- `README.md` описує відновлення worktree після clone, а `AGENTS.md` вимагає постійно читати актуальну KB перед змістовною роботою та оновлювати предметні документи, `status.md` і цей дайджест у тій самій задачі.

### Основні файли

- `architecture.md` — межі модулів і рекомендований потік.
- `data_contract.md` — точний контракт повідомлень і process boundary.
- `backlog.md`, `testing.md` — зведення звітів і історичних вимог.
- `system.md` — кодова реальність MLT-5.
- `decisions.md` — мотивація прийнятих/рекомендованих рішень.
- `status.md` — актуальний handover і відкриті питання.

### Синхронізація між агентами та live Jira

- Додано `collaboration.md` як спільний протокол для всіх агентів: pull-before-read, окремі worktree для паралельних незакомічених змін, fetch/rebase перед push, семантичне злиття та перевірка remote hash. `AGENTS.md` вимагає застосовувати його без запитів до розробника щодо редакційних Git-конфліктів.
- `README.md` тепер вимагає синхронізувати `origin/kb-only` перед читанням і пушити значущі KB-оновлення. У `decisions.md` зафіксовано автономне вирішення агентом конфліктів KB.
- Створено `jira.md`: live-запити 2026-11-08 підтвердили REST account `200`, проєкт key `MLT` з API-назвою `Muliprosessing-Analisis` і board ID 3 `MLT board`. Поточні issue statuses не завантажувалися. У KB не записувалися account email або API token.
- Оновлено `status.md`/`backlog.md`, щоб відрізняти підтверджену project identity від історичних issue-status зображень у звітах. Live API project name відрізняється написанням від назви у DOCX; для зіставлення використовуй key `MLT`.
- Перед редагуванням `kb-only` синхронізовано fetch-ем; branch був актуальний відносно `origin/kb-only`. Код не змінювався. Усі ці знання належать лише KB orphan-гілці; після оновлення її hash перевіряється окремо від `main`.
