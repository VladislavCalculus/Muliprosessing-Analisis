# Дайджест змін

## 2026-11-08 — two-terminal smoke підтвердив AudioPacket → MLT-5 без нових файлів

- Тимчасовий PCM16/8000 Hz/440 Hz fixture створено FFmpeg; Ncat через `127.0.0.1` передав pickle `AudioPacket` із першого процесу до другого, де `process_signal` повернув 440 Hz, 8000 frames/1.0 s і amplitude `0.12497339495662549`. Це тільки smoke transport, не application protocol; у repository файлів не додано.
- Після merge `mlt-4-wav` повний suite повторно пройшов: 18 passed за 4.62 s. Jira та main code не змінювалися. Див. точний evidence/межі в `testing.md`.

## 2026-11-08 — MLT-4 WAV reader злито в main без додаткового pipeline

- `mlt-4-wav` merged у `main` commit `85ce596` без конфліктів; remote `main` на `f73be7c` підтверджений. Додатковий `audio_pipeline` commit `db974ab` скасований новим revert-комітом за звуженим запитом користувача; цей код, CLI і чотири pipeline tests відсутні у поточному tree.
- `audio_io` тепер інтегрований у main поруч із `audio_contracts` і `signal_proc`. Попередній MLT-4 candidate suite був 18/18; поточний вузький merge крок повторного запуску suite не включав. Jira не змінювали.
- `read_wav_batch` залишається послідовним; MLT-2 worker scheduling, PCM formats besides tested fixtures, truncated WAV case та MLT-3 UI лишаються відкритими.

## 2026-11-08 — переглянуто `mlt-4-wav` проти Jira другого розробника

- Виявлено та fetch-нуто `origin/mlt-4-wav` (`94e9145`, після реалізації `0a36a7e`). Live REST JQL у MLT показав MLT-4 Epic `In Progress`, а MLT-6/7/8, MLT-26/27, MLT-30/31 — `To Do` для іншого розробника.
- Candidate branch додає `audio_io`, header/bounds validation, single-file decoding, ordered per-file batch errors і CLI. Незалежний статичний review не знайшов певного decode bug.
- Відкрите: MLT-27 паралельність відсутня; MLT-30 test не перевіряє structurally truncated WAV; заявлені PCM8/24/32 та IEEE float32/64 не мають fixture tests. 18 pytest cases пройшли (`PYTHONPATH=src python -m pytest -p no:cacheprovider test`); Jira не змінювали.

## 2026-11-08 — unit suite скорочено до 10 тестів за уточненням користувача

- Новий test file містить рівно 10 pytest cases; до запуску `pytest --collect-only` підтвердив кількість, а очікування звірено з реалізацією, Jira MLT-32/33 та числовими характеристиками FFT/фільтрів/PCM. Результат: 10 passed; test source не змінювався після першого запуску.
- Coverage.py 7.17.2: 97% combined statement/branch coverage для `signal_proc` (154 statements, 56 branches; 4 пропущені statements, 3 partial branches). Пропуски описані в `testing.md` і `test/README.md`.
- Незалежний review не знайшов blocker/high findings для 10 кейсів. Nyquist production fix збережений; зайву однокадрову coverage-only умову повернуто до попередньої перевірки за сумою вікна. Jira MLT-14 не переведено у Done, бо issue також згадує відсутній WAV parser.

## 2026-11-08 — MLT-5 unit suite пройшов із 100% statement/branch coverage

- Додано 45 pytest cases для конфіг-валідації, PCM, low/high-pass, even/odd FFT, Nyquist, peak threshold/range/separation, stereo, input immutability, payload і pickle. Два test doubles — SOS stub і `unittest.mock.Mock`; різні assertion APIs описані у `test/README.md`.
- Перший запуск: 44 passed, 1 failed — тест чистого Nyquist тону показав втрату endpoint plateau. Виправлено production code, не тести; після цього 45/45 пройшли.
- Coverage review також зробив однокадровий window fallback явним: SciPy Hann(1) уже має значення 1, тому зміна зберігає результат, але окремо покриває гілку безпечної нормалізації.
- Coverage.py 7.17.2, branch mode: `signal_proc/processing.py` 154 statements і 56 branches — 100%, без пропусків; пакетний `__init__.py` також 100%. Test source hashes до/після запуску не змінилися.
- Packaging verification: wheel `mlt_signal_processing-0.1.0-py3-none-any.whl` успішно зібрано через `pip wheel --no-deps --no-build-isolation .` після встановлення `setuptools 84.2.1` у `.venv`.
- Незалежний review підтвердив коректність тестів у межах `signal_proc` без blocker/high findings. Jira MLT-14 лишається To Do, бо її опис охоплює також відсутній WAV parser; див. межі у `testing.md`.
- Тести охоплюють обраний `signal_proc`, але не WAV parsing, якого поки немає. Jira MLT-14 лишається `To Do`; write у Jira не робили.
- Джерела і деталі — в `testing.md`; suite commands і optional dependencies — `test/README.md`, `pyproject.toml`.

## 2026-11-08 — підготовлено pytest suite для `signal_proc` перед першим запуском

- Додано MLT-5 host-only unit suite під `test/`, `python3 test/run_tests.py`, optional test dependencies та line/branch Coverage.py конфігурацію.
- До запуску вручну звірено expected values з API/алгоритмами, Jira MLT-32/33 acceptance criteria та офіційними pytest/mock/coverage docs. Є різні assert APIs і два test doubles: SOS-construction stub та `Mock` для filtering dependency.
- Test source статично скомпільовано; pytest і coverage ще не запускали. WAV parser виключений зі scope, бо MLT-4 reader відсутній.
- Рішення та методичні джерела — у `testing.md`; test entrypoint — у `test/README.md`.

## 2026-11-08 — використано Jira REST fallback і звірено Sprint 1 tasks з MLT-5

- Після початкової невдалої спроби через MCP/Docker використано наявні project-local credentials через read-only Jira Cloud REST API; автентифікований account збігається з раніше заданим. У project-local інструкціях зафіксовано MLT-scoped REST fallback, тож Docker не потрібен для майбутнього Jira читання.
- Live Sprint 1 snapshot: board 3, sprint ID 1 `active` попри завершений end date 2026-10-04; 15 issues загалом, 8 призначені цьому акаунту (MLT-9/10/11, MLT-23/24/25, MLT-32/33), усі `To Do`. Перелік і priorities — `backlog.md`; жодних Jira writes не виконано.
- Acceptance criteria stories MLT-23/24/25 звірено з MLT-5. Фільтр/FFT/піки реалізовані в бібліотечному модулі; full user journey обмежений відсутністю WAV reader та UI, а окремого disk persistence немає.
- Точні Jira bug criteria MLT-32/33 виконані на коді з `fadd1ec`: 440 Hz при 800 kHz повернувся точно; суміш 200 Hz/1.0 + 600 Hz/0.5 повернула піки в очікуваному порядку. Поточний defect не відтворено; Jira статуси лишились To Do. MLT-30/31 не перевірені, бо WAV reader ще відсутній.

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

## 2026-11-08 — оформлено протокол unit-тестів MLT-5

- Додано `docs/MLT5_unit_test_protocol.docx` у робоче дерево `main`: 10 тестових функцій `signal_proc`, assertions, два test doubles, покриття та повний test source appendix. Додаток перевірено на точну відповідність `test/test_signal_proc.py` (258 рядків).
- Coverage.py 7.17.2 повторно запущено з окремим тимчасовим data file, щоб не змінювати існуючий `.coverage`: 10 passed за 3.23 s; 97% combined statement/branch coverage; 4 непокриті statements і 3 partial branches.
- Google Classroom plugin/connector не знайдений через Plugin Management; документ залишений локально готовим до подання. Jira не запитувалась і не змінювалась.
- Перший `git fetch` у звичайному sandbox був заблокований OS permission error під час запису `FETCH_HEAD`. Перед публікацією авторизований fetch успішно звірив remote: `origin/kb-only` лишився на `5e9af55`; локальна гілка була один commit попереду, push і фінальна перевірка ще очікують.
