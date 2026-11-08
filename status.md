# Поточний стан

Остання звірка: 2026-11-08. Зміст цього файлу — точка відліку на дату звірки; актуальніше локальне дерево завжди перевіряй перед дією.

## Перевірена реалізація

- Гілка проєкту `main` на `origin/main` має коміт `fadd1ec` (`Fix peak filtering within selected frequency range`); попередній `6e6cbb1` (`Ignore project-local Codex configuration`).
- Реалізовані пакети: `src/audio_contracts/` (`AudioPacket`, `AudioReadError`, `AudioReadResult`) і `src/signal_proc/` (MLT-5). `process_signal` приймає `AudioPacket`; реалізує integer PCM → float64, optional Butterworth low/high-pass, Hann-window one-sided FFT та per-channel peak detection.
- Editable package build і компіляція вихідних Python-файлів проходили після зміни package layout. У коміті `fadd1ec` виправлено відбір піків у `src/signal_proc/processing.py`; inline числові перевірки PR3 TC-01…12, два регресійні сценарії, Jira MLT-32/33 exact criteria та `py_compile` пройшли. Для нової задачі створено pytest suite у `test/`; його перший запуск і coverage measurement ще очікують встановлення optional залежностей.
- MLT-4 WAV reader, MLT-2 worker orchestration, MLT-3 presentation і MLT-1 test/performance stage у цьому checkout ще не реалізовані. Їхні межі описані як контракт або рекомендований план у `architecture.md`, `data_contract.md` та `decisions.md`.

## Контракт модулів

- Успішне читання одного файла — один `AudioPacket` schema 1; невдача — `AudioReadError` із тим самим `source_id`. `signal_proc` не відкриває файли.
- `AudioPacket.samples` має непорожню форму `(frames, channels)` і C-contiguous layout. Integer масштаб зберігається на межі, float не нормалізується автоматично; масив у frozen dataclass технічно лишається mutable.
- Для багатопроцесної системи рекомендовано передавати parent→worker лише легкий file descriptor. Worker виконує MLT-4 → MLT-5 локально, а назовні повертає результат/помилку з `source_id`. Це архітектурне рішення ще не реалізоване.
- Пакети v1 не є HTTP/JSON схемою: `to_payload()` зберігає ndarray як ndarray. Великі масиви не кодувати в JSON/base64; shared memory — лише після benchmark.

## Звітні вимоги та перевірки

- Live read-only REST перевірка 2026-11-08 підтвердила project `MLT`, board `MLT board` ID 3 та Sprint 1 ID 1. Sprint має state `active`, хоча end date 2026-10-04 уже минув; у ньому 15 issues, з яких 8 призначені автентифікованому акаунту. Деталі — в `jira.md` і `backlog.md`; акаунтні PII не зберігаються.
- KB містить вимоги й план тестування PR1–PR4. Вкладені screenshots показують лише історичний стан на момент створення звітів; не трактуй їх як поточні Jira issue statuses.
- Docker/MCP handshake лишається недоступним, але це не блокує роботу: збережені credentials дали live REST read доступ. Локальні деталі й fallback workflow — в ignored `.codex/JIRA-STATUS.md` та `.codex/JIRA-INSTRUCTIONS.md`.
- Для вибраних MLT задач зафіксовано рольовий delivery workflow: live fetch, реалізація, незалежний review, evidence-based Bug creation і перевірений terminal transition. Точні локальні Codex agent TOML/MCP filters зберігаються лише в ignored `.codex/`; фактичний Jira status workflow ще треба звірити під час першої операції.
- У цьому аналізі Jira issues не створювалися, status/resolution не змінювалися; усі вісім призначених issues повернули `To Do`. Codex MCP handshake не потрібен для read-only REST fallback.
- 12 test cases, 18 checklist пунктів і 4 potential bugs описані в `testing.md`. Поточний точний replay MLT-32/33 пройшов; MLT-30/31 лишаються неперевіреними через відсутність WAV reader.
- Поточний read-only огляд коду підтвердив лише `audio_contracts` і `signal_proc`; MLT-4 WAV reader не існує. Один підтверджений edge-case bug у фільтрації піків виправлено; до/після докази й фактичні результати MLT-5 — у `testing.md`. Поточний pytest suite у `test/` написаний, але ще не запускався.
- Глобальний поріг допустимої похибки DSP і мінімальний speedup не визначені; не вводити їх як прийняті критерії без рішення команди.

## Git і база знань

- KB публікується лише в orphan-гілці `kb-only` того самого remote, що й `main`; локальний `knowledge-base/` має бути linked worktree того самого репозиторію. Дерева `main` і `kb-only` ізольовані й не мають спільного предка.
- У KB-гілці дозволені тільки її Markdown-документи; код, тестові файли й конфігурація проєкту належать до `main`. `knowledge-base/` і локальний `AGENTS.md` ігноруються кореневим `.gitignore`.
- `AGENTS.md` (локальний/ignored) і `collaboration.md` задають pull-before-read, fetch-before-push, rebase, conflict resolution та hash verification між агентами.

## Робоче дерево та handover

- У поточному локальному checkout є незакомічене видалення `tools/build_mlt5_protocol.py`. Це зміна користувача; не відновлювати автоматично й не включати в сторонній коміт. У `origin/main` на даті звірки старий файл ще присутній і використовує попередній `mlt_signal`/direct-array API, тому його сумісність із новим `AudioPacket` контрактом не підтверджена.
- Перед наступною інтеграцією перевір усі приклади, генератори та інші споживачі старого API. Окремо з’ясуй долю локально видаленого генератора; не роби висновків про нього з наявності в remote.
- Jira live fetch завершено; цей запит був read-only аналізом. Для повного user journey MLT-23/24/25 у checkout бракує MLT-4 WAV reader та MLT-3 UI/presentation; пріоритет/реалізацію наступних задач визначати за актуальним Jira scope.
- Поточний користувацький checkout має незакомічене видалення `tools/build_mlt5_protocol.py`; це не пов’язано з Jira review і не змінювати автоматично.

## Межі достовірності

Звіти й Jira screenshots, надані користувачем, описують теоретичний план, вимоги та знімки стану, а не поточну реалізацію. Код і Git-історію перевіряй у фактичному checkout. Якщо висновок не відтворено/не виміряно, залишай його непідтвердженим.
