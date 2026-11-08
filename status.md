# Поточний стан

Остання звірка: 2026-11-08, `main@f73be7c` / `origin/main@f73be7c`. Актуальніше локальне дерево завжди перевіряй перед дією.

## Перевірена реалізація

- `origin/main` на `f73be7c` містить merge commit `85ce596` для MLT-4 reader. `db974ab` (додатковий HTTP pipeline) скасовано звичайним revert-комітом `f73be7c` на прохання користувача; код `audio_pipeline` у поточному tree відсутній.
- У `main` реалізовані `audio_contracts`, `audio_io` (MLT-4 WAV reader) і `signal_proc` (MLT-5). Reader повертає `AudioPacket` або `AudioReadError`; `process_signal` виконує integer PCM → float64, optional Butterworth low/high-pass, Hann-window one-sided FFT та per-channel peak detection.
- Editable package build і компіляція Python-файлів проходили після зміни package layout; wheel build (`pip wheel --no-deps --no-build-isolation .`, setuptools 84.2.1) успішна. Коміт `fadd1ec` містить range/separation fix. Поточний suite має 10 pytest cases, 10/10 пройшли; Coverage.py для `signal_proc` — 97% combined statement/branch coverage (154 statements, 56 branches; 4 statements пропущені, 3 гілки частково покриті). У `src/signal_proc/processing.py` залишено Nyquist endpoint fix; coverage-only однокадрову зміну прибрано.
- Merge `mlt-4-wav` пройшов без конфліктів; на самій гілці до merge було 18/18 tests. `read_wav_batch` послідовний. MLT-2 worker pool, MLT-3 UI, formats besides tested PCM16 і structurally truncated WAV fixture лишаються відкритими.

## Контракт модулів

- Успішне читання одного файла — один `AudioPacket` schema 1; невдача — `AudioReadError` із тим самим `source_id`. `audio_io` читає файли; `signal_proc` працює лише з packet.
- `AudioPacket.samples` має непорожню форму `(frames, channels)` і C-contiguous layout. Integer масштаб зберігається на межі, float не нормалізується автоматично; масив у frozen dataclass технічно лишається mutable.
- Для багатопроцесної системи рекомендовано передавати parent→worker лише легкий file descriptor. Worker виконує MLT-4 → MLT-5 локально, а назовні повертає результат/помилку з `source_id`. Це архітектурне рішення ще не реалізоване.
- Пакети v1 не є HTTP/JSON схемою: `to_payload()` зберігає ndarray як ndarray. Великі масиви не кодувати в JSON/base64; shared memory — лише після benchmark. Додатковий HTTP pipeline, що тимчасово був у `db974ab`, скасований і не є чинним інтерфейсом.

## Звітні вимоги та перевірки

- Live read-only REST перевірка 2026-11-08 підтвердила project `MLT`, board `MLT board` ID 3 та Sprint 1 ID 1. Sprint має state `active`, хоча end date 2026-10-04 уже минув; у ньому 15 issues, з яких 8 призначені автентифікованому акаунту. Деталі — в `jira.md` і `backlog.md`; акаунтні PII не зберігаються.
- Новий live MLT-scoped JQL fetch повернув 17 відкритих assigned issues; 8 належать іншому розробнику: MLT-4 Epic `In Progress`, MLT-6/7/8, MLT-26/27 і MLT-30/31 — `To Do`. Branch-to-criteria mapping і невиконана MLT-27 parallelism вимога — у `backlog.md`/`testing.md`.
- KB містить вимоги й план тестування PR1–PR4. Вкладені screenshots показують лише історичний стан на момент створення звітів; не трактуй їх як поточні Jira issue statuses.
- Docker/MCP handshake лишається недоступним, але це не блокує роботу: збережені credentials дали live REST read доступ. Локальні деталі й fallback workflow — в ignored `.codex/JIRA-STATUS.md` та `.codex/JIRA-INSTRUCTIONS.md`.
- Для вибраних MLT задач зафіксовано рольовий delivery workflow: live fetch, реалізація, незалежний review, evidence-based Bug creation і перевірений terminal transition. Точні локальні Codex agent TOML/MCP filters зберігаються лише в ignored `.codex/`; фактичний Jira status workflow ще треба звірити під час першої операції.
- Під час попереднього Sprint 1 огляду Jira issues не створювалися й статуси не змінювалися; тоді 8 issues, призначених автентифікованому акаунту, повернули `To Do`. У цьому branch review також не було Jira writes.
- 12 test cases, 18 checklist пунктів і 4 potential bugs описані в `testing.md`. MLT-32/33 numeric replay пройшов; після merge MLT-4 у suite є reader tests для invalid і zero-byte WAV, але fixture structurally truncated WAV лишається відсутнім.
- `main` містить `audio_contracts`, `audio_io`, `signal_proc`; suite має 18 cases (6 reader, 2 CLI, 10 DSP). Попередній прогін окремої гілки завершився 18/18; у цій merge-only роботі suite повторно не запускався. MLT-5 coverage — раніше виміряні 97% у його окремому scope.
- Глобальний поріг допустимої похибки DSP і мінімальний speedup не визначені; не вводити їх як прийняті критерії без рішення команди.

## Git і база знань

- KB публікується лише в orphan-гілці `kb-only` того самого remote, що й `main`; локальний `knowledge-base/` має бути linked worktree того самого репозиторію. Дерева `main` і `kb-only` ізольовані й не мають спільного предка.
- У KB-гілці дозволені тільки її Markdown-документи; код, тестові файли й конфігурація проєкту належать до `main`. `knowledge-base/` і локальний `AGENTS.md` ігноруються кореневим `.gitignore`.
- `AGENTS.md` (локальний/ignored) і `collaboration.md` задають pull-before-read, fetch-before-push, rebase, conflict resolution та hash verification між агентами.

## Робоче дерево та handover

- У поточному локальному checkout є незакомічене видалення `tools/build_mlt5_protocol.py`. Це зміна користувача; не відновлювати автоматично й не включати в сторонній коміт. У `origin/main` на даті звірки старий файл ще присутній і використовує попередній `mlt_signal`/direct-array API, тому його сумісність із новим `AudioPacket` контрактом не підтверджена.
- Перед наступною інтеграцією перевір усі приклади, генератори та інші споживачі старого API. Окремо з’ясуй долю локально видаленого генератора; не роби висновків про нього з наявності в remote.
- `main` тепер має WAV reader та MLT-4 CLI разом із MLT-5; MLT-3 UI/presentation і окрема інтеграція модулів у UI лишаються відсутні. Merge не змінював Jira.
- За останнім live snapshot перед merge Jira MLT-14 `Створити unit-тести` перебувала `To Do`, Medium, parent MLT-1 і не була призначена автентифікованому акаунту; користувач окремо поставив `signal_proc` scope. Статус після цієї кодової інтеграції повторно не запитувався й не змінювався. Reader review/test evidence — у `testing.md`.
- MLT-4 reader опублікований у `origin/main` через merge commit `85ce596`; надлишковий pipeline commit revert-нуто `f73be7c`, щоб залишити лише запитаний merge. У кореневому worktree лишилося лише раніше наявне локальне видалення `tools/build_mlt5_protocol.py`.
- Поточний користувацький checkout має незакомічене видалення `tools/build_mlt5_protocol.py`; це не пов’язано з Jira review і не змінювати автоматично.

## Межі достовірності

Звіти й Jira screenshots, надані користувачем, описують теоретичний план, вимоги та знімки стану, а не поточну реалізацію. Код і Git-історію перевіряй у фактичному checkout. Якщо висновок не відтворено/не виміряно, залишай його непідтвердженим.
