# MLT-4 and MLT-5 tests

Тести навмисно залишені компактними: перевіряються основні сценарії, потрібні
для модуля MLT-4, без великої кількості рідкісних крайових випадків.

У наборі **18 pytest-перевірок**:
- 6 перевірок читання WAV у `test_audio_io.py`;
- 2 перевірки консольного запуску в `test_audio_io_cli.py`;
- 10 наявних перевірок математичного модуля MLT-5 у `test_signal_proc.py`.

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
