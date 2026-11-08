# Поточний стан

Остання звірка: 2026-11-08. Зміст цього файлу — точка відліку на дату звірки; актуальніше локальне дерево завжди перевіряй перед дією.

## Перевірена реалізація

- Гілка проєкту `main` на `origin/main` має коміт `55ac0b2` (`Add ten unit tests for signal_proc`); попередні `fadd1ec` (`Fix peak filtering within selected frequency range`) та `6e6cbb1` (`Ignore project-local Codex configuration`).
- Реалізовані пакети: `src/audio_contracts/` (`AudioPacket`, `AudioReadError`, `AudioReadResult`) і `src/signal_proc/` (MLT-5). `process_signal` приймає `AudioPacket`; реалізує integer PCM → float64, optional Butterworth low/high-pass, Hann-window one-sided FFT та per-channel peak detection.
- Editable package build і компіляція Python-файлів проходили після зміни package layout; wheel build (`pip wheel --no-deps --no-build-isolation .`, setuptools 84.2.1) успішна. Коміт `fadd1ec` містить range/separation fix. Поточний suite має 10 pytest cases, 10/10 пройшли; Coverage.py для `signal_proc` — 97% combined statement/branch coverage (154 statements, 56 branches; 4 statements пропущені, 3 гілки частково покриті). У `src/signal_proc/processing.py` залишено Nyquist endpoint fix; coverage-only однокадрову зміну прибрано.
- У `main` ще немає MLT-4 WAV reader, MLT-2 worker orchestration чи MLT-3 UI. Окрема remote `mlt-4-wav` на `94e9145` додає `audio_io`; ця гілка пройшла статичний review і 18 тестів, але не злита у `main`. Паралельність MLT-27 і широкий format/truncation coverage лишилися відкритими.

## Контракт модулів

- Успішне читання одного файла — один `AudioPacket` schema 1; невдача — `AudioReadError` із тим самим `source_id`. `signal_proc` не відкриває файли.
- `AudioPacket.samples` має непорожню форму `(frames, channels)` і C-contiguous layout. Integer масштаб зберігається на межі, float не нормалізується автоматично; масив у frozen dataclass технічно лишається mutable.
- Для багатопроцесної системи рекомендовано передавати parent→worker лише легкий file descriptor. Worker виконує MLT-4 → MLT-5 локально, а назовні повертає результат/помилку з `source_id`. Це архітектурне рішення ще не реалізоване.
- Пакети v1 не є HTTP/JSON схемою: `to_payload()` зберігає ndarray як ndarray. Великі масиви не кодувати в JSON/base64; shared memory — лише після benchmark.

## Звітні вимоги та перевірки

- Live read-only REST перевірка 2026-11-08 підтвердила project `MLT`, board `MLT board` ID 3 та Sprint 1 ID 1. Sprint має state `active`, хоча end date 2026-10-04 уже минув; у ньому 15 issues, з яких 8 призначені автентифікованому акаунту. Деталі — в `jira.md` і `backlog.md`; акаунтні PII не зберігаються.
- Новий live MLT-scoped JQL fetch повернув 17 відкритих assigned issues; 8 належать іншому розробнику: MLT-4 Epic `In Progress`, MLT-6/7/8, MLT-26/27 і MLT-30/31 — `To Do`. Branch-to-criteria mapping і невиконана MLT-27 parallelism вимога — у `backlog.md`/`testing.md`.
- KB містить вимоги й план тестування PR1–PR4. Вкладені screenshots показують лише історичний стан на момент створення звітів; не трактуй їх як поточні Jira issue statuses.
- Docker/MCP handshake лишається недоступним, але це не блокує роботу: збережені credentials дали live REST read доступ. Локальні деталі й fallback workflow — в ignored `.codex/JIRA-STATUS.md` та `.codex/JIRA-INSTRUCTIONS.md`.
- Для вибраних MLT задач зафіксовано рольовий delivery workflow: live fetch, реалізація, незалежний review, evidence-based Bug creation і перевірений terminal transition. Точні локальні Codex agent TOML/MCP filters зберігаються лише в ignored `.codex/`; фактичний Jira status workflow ще треба звірити під час першої операції.
- Під час попереднього Sprint 1 огляду Jira issues не створювалися й статуси не змінювалися; тоді 8 issues, призначених автентифікованому акаунту, повернули `To Do`. У цьому branch review також не було Jira writes.
- 12 test cases, 18 checklist пунктів і 4 potential bugs описані в `testing.md`. Поточний точний replay MLT-32/33 пройшов; MLT-30/31 лишаються неперевіреними через відсутність WAV reader.
- `main` містить `audio_contracts` і `signal_proc`; MLT-4 candidate існує лише в `origin/mlt-4-wav`. MLT-5 має 10/10 unit tests і 97% combined statement/branch coverage; candidate branch test details — у `testing.md`.
- Глобальний поріг допустимої похибки DSP і мінімальний speedup не визначені; не вводити їх як прийняті критерії без рішення команди.

## Git і база знань

- KB публікується лише в orphan-гілці `kb-only` того самого remote, що й `main`; локальний `knowledge-base/` має бути linked worktree того самого репозиторію. Дерева `main` і `kb-only` ізольовані й не мають спільного предка.
- У KB-гілці дозволені тільки її Markdown-документи; код, тестові файли й конфігурація проєкту належать до `main`. `knowledge-base/` і локальний `AGENTS.md` ігноруються кореневим `.gitignore`.
- `AGENTS.md` (локальний/ignored) і `collaboration.md` задають pull-before-read, fetch-before-push, rebase, conflict resolution та hash verification між агентами.

## Робоче дерево та handover

- У поточному локальному checkout є незакомічене видалення `tools/build_mlt5_protocol.py`. Це зміна користувача; не відновлювати автоматично й не включати в сторонній коміт. У `origin/main` на даті звірки старий файл ще присутній і використовує попередній `mlt_signal`/direct-array API, тому його сумісність із новим `AudioPacket` контрактом не підтверджена.
- Перед наступною інтеграцією перевір усі приклади, генератори та інші споживачі старого API. Окремо з’ясуй долю локально видаленого генератора; не роби висновків про нього з наявності в remote.
- Для повного user journey MLT-23/24/25 у `main` бракує MLT-4 WAV reader та MLT-3 UI/presentation; окремий MLT-4 branch це лише частково закриває. Jira live fetch цього огляду був read-only.
- За останнім live snapshot Jira MLT-14 `Створити unit-тести` перебуває `To Do`, Medium, parent MLT-1 і не призначена автентифікованому акаунту; користувач окремо поставив її для `signal_proc`. Цей scope пройшов review; новий WAV-reader candidate має власний review/test результат, але Jira статус не змінювався. Деталі — у `testing.md`.
- MLT-5 unit suite і Nyquist fix запушені в `main` комітом `55ac0b2`; KB MLT-5 update — `kb-only` комітом `3495d68`. У кореневому user worktree лишилося лише раніше наявне локальне видалення `tools/build_mlt5_protocol.py`; review worktree на MLT-4 branch не редагувався.
- Поточний користувацький checkout має незакомічене видалення `tools/build_mlt5_protocol.py`; це не пов’язано з Jira review і не змінювати автоматично.

## Межі достовірності

Звіти й Jira screenshots, надані користувачем, описують теоретичний план, вимоги та знімки стану, а не поточну реалізацію. Код і Git-історію перевіряй у фактичному checkout. Якщо висновок не відтворено/не виміряно, залишай його непідтвердженим.
