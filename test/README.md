# MLT: перевірки WAV, DSP, паралельної обробки та SQLite

Тести навмисно залишені компактними: перевіряються основні сценарії, потрібні
для модуля MLT-4, без великої кількості рідкісних крайових випадків.

У наборі **45 pytest-перевірок**:
- 6 перевірок читання WAV у `test_audio_io.py`;
- 2 перевірки консольного запуску в `test_audio_io_cli.py`;
- 10 наявних перевірок математичного модуля MLT-5 у `test_signal_proc.py`.
- 4 перевірки descriptor-а та виконання одного файла MLT-2 у `test_batch_worker.py`.
- 3 перевірки життєвого циклу spawn-пулу в `test_batch_pool.py`.
- 3 перевірки розподілу й кореляції batch у `test_batch_schedule.py`.
- 3 перевірки збору повних результатів у `test_batch_collect.py`.
- 3 перевірки ізоляції аварійного завершення в `test_batch_failures.py`.
- 9 перевірок реальної SQLite у `test_result_store.py`.
- 2 перевірки batch CLI та історії в `test_batch_cli.py`.

## Що перевіряє MLT-4

1. правильний mono WAV: 8000 Гц, 1 канал, 16 біт, 1 с;
2. правильний stereo WAV: 16000 Гц, 2 канали, 16 біт, 2 с;
3. пошкоджений файл між двома правильними не зупиняє останній файл;
4. порожній файл повертає `empty_audio`;
5. відсутній файл повертає `read_failed`;
6. прочитаний WAV передається в реальний MLT-5 і для тону 440 Гц знаходиться пік;
7. консоль показує параметри правильного файла;
8. консоль показує помилку середнього файла й усе одно читає наступний.

## Запуск

З кореня проєкту:

```sh
python -m pip install -e '.[test]'
python -m pytest test
```

Ці вісім перевірок MLT-4 є скороченим набором основних сценаріїв.

## Обраний модуль для практичної роботи: MLT-5

Для завдання достатньо наявних **10 тестів** у `test_signal_proc.py`.
Вони перевіряють FFT і порядок піків, незалежність каналів, реальні low/high-pass
фільтри, нормалізацію PCM, непарну довжину FFT, Найквіст/один кадр/тишу,
правила пошуку піків, помилки аргументів і payload/pickle.

Використано точну рівність, порівняння `>`/`<`, ідентичність `is`,
`pytest.approx`, `np.testing.assert_array_equal`, `pytest.raises` і
`Mock.assert_called_once`. Двійники в `test_filter_backend_uses_stub_and_mock`:
`butter_stub` повертає контрольований SOS-маркер; `Mock` підмінює `sosfilt`,
повертає задані кадри та реєструє виклик. `monkeypatch` відновлює залежності.

Після активації `.venv` окремий прогін і вимірювання:

```sh
python -m coverage run --branch --source=signal_proc -m pytest -p no:cacheprovider test/test_signal_proc.py -v
python -m coverage report -m
python -m coverage html -d htmlcov/signal_proc
```

Результат 2026-11-23: **10 passed in 3.13s**. Покрито 152/156 операторів
(97,44%) та 53/56 переходів (94,64%); сумарно Coverage.py — **96,70%**,
у консольному звіті округлено до **97%**. Scope: тільки `signal_proc`;
`audio_contracts`, `audio_io` і бібліотеки не включені. Пропуски:
`processing.py:194–195,218–219` і перехід `243→245`.

Повний host-only набір запускається командою `python test/run_tests.py`;
він також включає MLT-4 із тимчасовими WAV-файлами. Поточний контрольний
прогін `python -m pytest -p no:cacheprovider test -v` через Coverage.py:
**18 passed in 4.63s**. Тестові файли в цій роботі не змінювалися.

## MLT-2: контракт і виконання одного файла

`test_batch_worker.py` перевіряє pickle/frozen `FileJob`, реальний WAV → DSP
зі збереженням початкового файла, кореляцію read/DSP errors і продовження
наступного завдання, а також ізоляцію неочікуваного звичайного DSP винятку.
Цей етап не перевіряє пул або аварійне завершення worker-процесу.

```sh
PYTHONPATH=src python -m pytest -p no:cacheprovider test/test_batch_worker.py -q
```

Фактичний прогін 2026-11-24: **4 passed in 2.61s**. Додаткова не-тестова
перевірка `python -m compileall -q src/audio_contracts/jobs.py src/batch_proc`
завершилася успішно.

`test_batch_pool.py` запускає два реальні spawn-процеси, перевіряє їх
повторне використання, завершення зайнятих worker-ів після винятку викликачa
та cleanup при частковій помилці запуску. Команда
`PYTHONPATH=src python -m pytest -p no:cacheprovider test/test_batch_pool.py -q`
дала **3 passed in 5.45s** (2026-11-24). `compileall` та
`git diff --check` успішні.

`test_batch_schedule.py` перевіряє справжній порядок завершення незалежно
від вхідного списку (перший worker очікує дозволу від parent), продовження
pending-файла після read error, а також перевірку всіх ID до створення
процесів і порожній batch. Команда
`PYTHONPATH=src python -m pytest -p no:cacheprovider test/test_batch_schedule.py -q`
дала **3 passed in 5.35s** (2026-11-24). Компіляція `src/batch_proc`
та `git diff --check` успішні.

`test_batch_collect.py` перевіряє збір повних кадрів/спектра/піків і read error
у parent, справжній PID виклику callback-а, cleanup після його винятку та
порожній агрегат. Команда
`PYTHONPATH=src python -m pytest -p no:cacheprovider test/test_batch_collect.py -q`
дала **3 passed in 4.26s** (2026-11-24); `compileall src/batch_proc` та
`git diff --check` успішні.

`test_batch_failures.py` виконує справжній `os._exit(23)` у одному worker-і,
перевіряє збереження PID іншого активного worker-а й обробку pending-файлів
заміною, втрату idle worker-а до assignment без втрати descriptor-а та
cleanup після дострокового закриття ітератора. Координаційні очікування
тестів мають deadline; production CLI не має crash-прапорців.
Команда `PYTHONPATH=src python -m pytest -p no:cacheprovider
test/test_batch_failures.py test/test_batch_pool.py test/test_batch_collect.py -q`
дала **9 passed in 14.59s** (2026-11-24); `compileall` та `git diff --check`
успішні.

## Протокол

Готові [PDF](../docs/unit_testing/protocol.pdf),
[DOCX](../docs/unit_testing/protocol.docx) і
[текст](../docs/unit_testing/protocol.txt) містять сценарії, assert, два
двійники, результати покриття та повний лістинг усіх 10 тестів.
Первинний вивід та параметри запуску — у `docs/unit_testing/pytest.txt`,
`coverage.txt`, `coverage.json`, `environment.json` (із SHA-256 вихідних файлів).

Для повторного формування звіту з цих доказів:

```sh
python -m pip install -r docs/unit_testing/requirements-report.txt
python docs/unit_testing/build_protocol.py
```

Для PDF потрібні Arial.ttf, Arial Bold.ttf та Courier New.ttf; типовий шлях —
`/System/Library/Fonts/Supplemental`. На іншій ОС передай
`--font-dir /path/to/fonts`. Генератор не запускає тести й перевіряє хеші
тестового файла та реалізації перед формуванням протоколу. Після змін коду
потрібно повторити вимірювання та оновити докази, зокрема `environment.json`.

## SQLite та збереження історії — 2026-11-24

`test_result_store.py` містить 9 перевірок реальної тимчасової SQLite:
два рівні master–detail, seed/JOIN і SQL-функції, поля/унікальність,
FK/cascade, тригери, стан запуску, rollback рядків і NPZ після помилки піка,
відновлення повних масивів після видалення WAV, історія та версія схеми.
Ще 2 subprocess-перевірки CLI — `test_batch_cli.py`.

```sh
PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider test/test_result_store.py -v
.venv/bin/python test/run_tests.py
```

Окремий DB-прогін: **9 passed in 1.51s**; повний набір через evidence runner:
**45 passed in 24.20s**. Незалежний review DB/CLI — PASS, 11 перевірок
пройшли за 9.84s; додатково відтворено видиму помилку запису артефакта
(CLI exit 2, запуск failed, без збережених результатів).

[Протокол і відтворення](../docs/database_testing/README.md) містять SQL,
лістинги, DOCX/PDF і збережені фактичні докази. Початкові 10 DSP-тестів
залишилися без змін; попереднє вимірювання їх coverage є датованим результатом.
