# Поточний стан

Остання звірка: 2026-11-08. Зміст цього файлу — точка відліку на дату звірки; актуальніше локальне дерево завжди перевіряй перед дією.

## Перевірена реалізація

- Гілка проєкту `main` на `origin/main` має коміт `a2ef008` (`Define audio packet contract and module layout`).
- Реалізовані пакети: `src/audio_contracts/` (`AudioPacket`, `AudioReadError`, `AudioReadResult`) і `src/signal_proc/` (MLT-5). `process_signal` приймає `AudioPacket`; реалізує integer PCM → float64, optional Butterworth low/high-pass, Hann-window one-sided FFT та per-channel peak detection.
- Editable package build і компіляція вихідних Python-файлів пройшли після зміни package layout. У package discovery входять `audio_contracts` і `signal_proc`. Тести не запускались у межах попереднього кодування; у цій роботі змін коду немає.
- MLT-4 WAV reader, MLT-2 worker orchestration, MLT-3 presentation і MLT-1 test/performance stage у цьому checkout ще не реалізовані. Їхні межі описані як контракт або рекомендований план у `architecture.md`, `data_contract.md` та `decisions.md`.

## Контракт модулів

- Успішне читання одного файла — один `AudioPacket` schema 1; невдача — `AudioReadError` із тим самим `source_id`. `signal_proc` не відкриває файли.
- `AudioPacket.samples` має непорожню форму `(frames, channels)` і C-contiguous layout. Integer масштаб зберігається на межі, float не нормалізується автоматично; масив у frozen dataclass технічно лишається mutable.
- Для багатопроцесної системи рекомендовано передавати parent→worker лише легкий file descriptor. Worker виконує MLT-4 → MLT-5 локально, а назовні повертає результат/помилку з `source_id`. Це архітектурне рішення ще не реалізоване.
- Пакети v1 не є HTTP/JSON схемою: `to_payload()` зберігає ndarray як ndarray. Великі масиви не кодувати в JSON/base64; shared memory — лише після benchmark.

## Звітні вимоги та перевірки

- KB містить карту Jira з PR1 та зафіксовані вимоги/план тестування PR2–PR4. Вкладені screenshots показують лише історичний стан на момент створення звітів; поточний Jira не перевірявся.
- 12 test cases, 18 checklist пунктів і 4 potential bugs описані в `testing.md`. Жоден кейс чи bug report не позначений як фактично виконаний/підтверджений звітами.
- Глобальний поріг допустимої похибки DSP і мінімальний speedup не визначені; не вводити їх як прийняті критерії без рішення команди.

## Git і база знань

- KB публікується лише в orphan-гілці `kb-only` того самого remote, що й `main`; локальний `knowledge-base/` має бути linked worktree того самого репозиторію. Дерева `main` і `kb-only` ізольовані й не мають спільного предка.
- У KB-гілці дозволені тільки її Markdown-документи; код, тестові файли й конфігурація проєкту належать до `main`. `knowledge-base/` і локальний `AGENTS.md` ігноруються кореневим `.gitignore`.
- Інструкція локального агента в корені вимагає читати цю KB на початку кожної змістовної задачі, підтримувати її під час роботи, оновлювати `status.md` + `changes.md` і пушити KB окремо в `origin/kb-only`.

## Робоче дерево та handover

- У поточному локальному checkout є незакомічене видалення `tools/build_mlt5_protocol.py`. Це зміна користувача; не відновлювати автоматично й не включати в сторонній коміт. У `origin/main` на даті звірки старий файл ще присутній і використовує попередній `mlt_signal`/direct-array API, тому його сумісність із новим `AudioPacket` контрактом не підтверджена.
- Перед наступною інтеграцією перевір усі приклади, генератори та інші споживачі старого API. Окремо з’ясуй долю локально видаленого генератора; не роби висновків про нього з наявності в remote.
- Наступний архітектурний етап — реалізувати MLT-4 адаптер WAV → `AudioPacket`/`AudioReadError`, після чого погодити й реалізувати MLT-2 file job/worker потік. Конкретний виконавець/строк Jira не перевірено.

## Межі достовірності

Звіти й Jira screenshots, надані користувачем, описують теоретичний план, вимоги та знімки стану, а не поточну реалізацію. Код і Git-історію перевіряй у фактичному checkout. Якщо висновок не відтворено/не виміряно, залишай його непідтвердженим.
