# Поточний стан

Остання звірка: 2026-11-08. Зміст цього файлу — точка відліку на дату звірки; актуальніше локальне дерево завжди перевіряй перед дією.

## Перевірена реалізація

- Гілка проєкту `main` на `origin/main` має коміт `6e6cbb1` (`Ignore project-local Codex configuration`); попередній кодовий коміт — `a2ef008` (`Define audio packet contract and module layout`).
- Реалізовані пакети: `src/audio_contracts/` (`AudioPacket`, `AudioReadError`, `AudioReadResult`) і `src/signal_proc/` (MLT-5). `process_signal` приймає `AudioPacket`; реалізує integer PCM → float64, optional Butterworth low/high-pass, Hann-window one-sided FFT та per-channel peak detection.
- Editable package build і компіляція вихідних Python-файлів проходили після зміни package layout. У цьому аудиті виправлено відбір піків у `src/signal_proc/processing.py`; inline числові перевірки PR3 TC-01…12, два додаткові регресійні сценарії та PR4 800k-frame тон пройшли. `py_compile` пройшов; окремої формальної `tests/` suite у checkout немає.
- MLT-4 WAV reader, MLT-2 worker orchestration, MLT-3 presentation і MLT-1 test/performance stage у цьому checkout ще не реалізовані. Їхні межі описані як контракт або рекомендований план у `architecture.md`, `data_contract.md` та `decisions.md`.

## Контракт модулів

- Успішне читання одного файла — один `AudioPacket` schema 1; невдача — `AudioReadError` із тим самим `source_id`. `signal_proc` не відкриває файли.
- `AudioPacket.samples` має непорожню форму `(frames, channels)` і C-contiguous layout. Integer масштаб зберігається на межі, float не нормалізується автоматично; масив у frozen dataclass технічно лишається mutable.
- Для багатопроцесної системи рекомендовано передавати parent→worker лише легкий file descriptor. Worker виконує MLT-4 → MLT-5 локально, а назовні повертає результат/помилку з `source_id`. Це архітектурне рішення ще не реалізоване.
- Пакети v1 не є HTTP/JSON схемою: `to_payload()` зберігає ndarray як ndarray. Великі масиви не кодувати в JSON/base64; shared memory — лише після benchmark.

## Звітні вимоги та перевірки

- Ідентифікацію live Jira зафіксовано в `jira.md`: 2026-11-08 попередній Jira REST-запит підтвердив project `MLT` (`Muliprosessing-Analisis`) і board `MLT board` ID 3. Під час поточного аудиту поточні issues/assignees отримати не вдалося: project-scoped MCP має стан `Unsupported`, а локальна команда `docker` відсутня. Не виводити персональне призначення з історичних звітів.
- KB містить вимоги й план тестування PR1–PR4. Вкладені screenshots показують лише історичний стан на момент створення звітів; не трактуй їх як поточні Jira issue statuses.
- Попередній REST доступ не означає, що live issue/sprint data доступні в цьому аудиті. MCP container handshake не пройшов через відсутню залежність Docker; локальні деталі підключення/хоста залишаються в ignored `.codex/JIRA-STATUS.md`.
- Для вибраних MLT задач зафіксовано рольовий delivery workflow: live fetch, реалізація, незалежний review, evidence-based Bug creation і перевірений terminal transition. Точні локальні Codex agent TOML/MCP filters зберігаються лише в ignored `.codex/`; фактичний Jira status workflow ще треба звірити під час першої операції.
- У цій роботі Jira issues не створювалися й їхні status/resolution не змінювалися. Codex workflow налаштовано, але Docker CLI відсутній; MCP handshake і фактична доступність Jira tools лишаються неперевіреними.
- 12 test cases, 18 checklist пунктів і 4 potential bugs описані в `testing.md`. Жоден кейс чи bug report не позначений як фактично виконаний/підтверджений звітами.
- Поточний read-only огляд коду підтвердив лише `audio_contracts` і `signal_proc`; директорії `tests/` немає. Один підтверджений edge-case bug у фільтрації піків виправлено; до/після докази й фактичні результати MLT-5 — у `testing.md`.
- Глобальний поріг допустимої похибки DSP і мінімальний speedup не визначені; не вводити їх як прийняті критерії без рішення команди.

## Git і база знань

- KB публікується лише в orphan-гілці `kb-only` того самого remote, що й `main`; локальний `knowledge-base/` має бути linked worktree того самого репозиторію. Дерева `main` і `kb-only` ізольовані й не мають спільного предка.
- У KB-гілці дозволені тільки її Markdown-документи; код, тестові файли й конфігурація проєкту належать до `main`. `knowledge-base/` і локальний `AGENTS.md` ігноруються кореневим `.gitignore`.
- `AGENTS.md` (локальний/ignored) і `collaboration.md` задають pull-before-read, fetch-before-push, rebase, conflict resolution та hash verification між агентами.

## Робоче дерево та handover

- У поточному локальному checkout є незакомічене видалення `tools/build_mlt5_protocol.py`. Це зміна користувача; не відновлювати автоматично й не включати в сторонній коміт. У `origin/main` на даті звірки старий файл ще присутній і використовує попередній `mlt_signal`/direct-array API, тому його сумісність із новим `AudioPacket` контрактом не підтверджена.
- Перед наступною інтеграцією перевір усі приклади, генератори та інші споживачі старого API. Окремо з’ясуй долю локально видаленого генератора; не роби висновків про нього з наявності в remote.
- У цій роботі є незакомічена зміна `src/signal_proc/processing.py` для виправлення peak range/separation; не переписувати її. Потрібна live Jira доступність, щоб визначити фактичні Sprint 1 issues, assignee та зіставити acceptance criteria з цим checkout.
- Наступний архітектурний етап у кодовому плані — реалізувати MLT-4 адаптер WAV → `AudioPacket`/`AudioReadError`, після чого погодити й реалізувати MLT-2 file job/worker потік. Пріоритет відносно першого спринту невідомий без live Jira.

## Межі достовірності

Звіти й Jira screenshots, надані користувачем, описують теоретичний план, вимоги та знімки стану, а не поточну реалізацію. Код і Git-історію перевіряй у фактичному checkout. Якщо висновок не відтворено/не виміряно, залишай його непідтвердженим.
