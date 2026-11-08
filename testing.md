# Тест-план, кейси й баг-репорти

## Статус доказів

Джерело тест-плану — TP-MLT-2026-001 v1.1 від 04.10.2026 (звіт PR2). Він описує заплановані перевірки; у звіті сказано, що показані Jira-задачі мали `To Do`, тому виконання треба підтвердити окремо. PR3 створює тест-кейси й checklist, але не містить заповнених фактичних результатів. PR4 прямо називає баги потенційними/Not tested.

Це специфікація очікувань, не результат тестування. У наявному checkout немає автоматизованих тестових файлів; цей аудит натомість виконав inline числові перевірки, описані нижче. PR3 викликає старий `process_signal(samples, fs, source_id=...)`; у поточному API треба використовувати `process_signal(AudioPacket(...))`.

## Обсяг

**Перевіряти за планом:** WAV читання та метадані; контрольовані помилки; фільтр без зміни оригінального файла; FFT, шкала частот і амплітуди; домінуючі піки; незалежність каналів; паралельна обробка кількох файлів; статуси/результати UI; послідовний проти паралельного часу.

**Не входить у зафіксований обсяг:** формати аудіо крім WAV; мережевий розподілений режим між комп’ютерами; збереження відфільтрованого WAV як окрема функція.

## Типи тестування й прив’язка

| Тип | Перевірка | Jira |
| --- | --- | --- |
| Unit | WAV parser, фільтрація, FFT, піки; звичайні, граничні й некоректні значення | MLT-14 |
| Integration | Пакет кількох файлів різного розміру, окремі результати й обробка помилок | MLT-15 |
| Performance | Однаковий набір файлів у serial і multiprocess; фіксувати умови та час | MLT-12 |
| Negative | Пошкоджений WAV, порожній вхід, некоректна частота/дані, помилка одного файла | MLT-14/15 |
| Regression | Повторити невдалий сценарій після виправлення й зачеплені перевірки | MLT-13 |
| UI/output | Метадані, статуси, прогрес, спектр, піки, фільтр | MLT-16/17/18/28 |

## Критерії з плану

### Успіх

- Підготовлені unit-тести мають фактичний результат, що відповідає очікуваному.
- Підтримуваний WAV читається; параметри відповідають файлу.
- Помилка одного файла не зупиняє інші без окремої причини.
- Оригінальний WAV не змінюється фільтрацією.
- FFT та піки збігаються з відомими тест-сигналами в узгодженому допуску.
- Serial і multiprocess порівняні на однакових даних; висновок про прискорення базується на замірах.
- Немає критичного відкритого дефекту, що блокує основний сценарій.

### Невдача

Аварійне завершення на коректному файлі/пакеті; помилка одного файла безпідставно валить batch; змінюється оригінал; не читаються параметри підтримуваного WAV; некоректні спектр/піки; UI-статус не відповідає дійсності; лишається блокувальний дефект.

### Не визначено глобально

TP-MLT-2026-001 не погоджує максимальну похибку FFT/фільтра та мінімальний speedup. Не вигадуй глобальний поріг. Числові допуски нижче — очікування окремих кейсів PR3.

## Середовище та тестові дані з плану

- Windows 10/11; Ubuntu лише якщо команда налаштувала це середовище.
- Багатоядерний комп’ютер, рекомендовано від 8 GB RAM.
- Python 3.x, pytest; NumPy, SciPy, Matplotlib відповідно до фактичної реалізації. Актуальний пакет в `pyproject.toml` вимагає Python `>=3.10`, NumPy `>=2.1,<3`, SciPy `>=1.15,<2`; Matplotlib не потрібен MLT-5.
- Валідні WAV різної тривалості й sample rate; у плані наведені 22.05, 44.1, 48 kHz за умови підтримки парсером. Також потрібні неповний/пошкоджений та 0-byte WAV.
- Для відомих DSP-сигналів PR3 бере `fs=8000 Hz`, `N=8000`, отже FFT-крок 1 Hz; використовуються синусоїди з точно відомими частотами/амплітудами.
- Порівняння швидкості має проходити на тих самих файлах і параметрах. Варто включити малі та великі файли: накладні витрати pool можуть зробити малі файли повільнішими.

## MLT-5 test cases з PR3

Усі кейси незалежні; очікувані винятки є успішним результатом лише там, де явно вказано негативний сценарій.

| ID | Вхід | Очікування з кейсу |
| --- | --- | --- |
| TC-01 | `fs=8000`, `N=8000`, синус 440 Hz, амплітуда 0.8 | 8000 кадрів, 1 канал, 1 s, FFT-крок 1 Hz; пік 440 Hz, amplitude `0.8 ± 0.02` |
| TC-02 | `0.8*sin(440)+0.3*sin(1000)` на тій самій сітці | Перші піки 440 Hz (`0.8 ± 0.02`), потім 1000 Hz (`0.3 ± 0.02`); порядок за amplitude |
| TC-03 | Ті самі тони; Butterworth low-pass 600 Hz, order 4 | 440 Hz `>0.65`, 1000 Hz `<0.05`; вхід побітово незмінний; конфіг записаний у результаті |
| TC-04 | Ті самі тони; high-pass 700 Hz, order 4 | 440 Hz `<0.20`, 1000 Hz `>0.25`; найбільший пік 1000 Hz |
| TC-05 | Stereo: канал 0 = 440 Hz/0.8, канал 1 = 1000 Hz/0.3 | `samples.shape==(8000,2)`, spectrum shape `(4001,2)`; піки окремі, без змішування каналів |
| TC-06 | `uint8`: `round(128 + 64*sin(440))` | Вихід `float64`, `(8000,1)`, пік 440 Hz `0.50 ± 0.03`; оригінальний uint8 незмінний |
| TC-07 | 256 нульових кадрів | Усі amplitudes 0, список піків порожній, без помилки/divide-by-zero |
| TC-08 | 1234.5 Hz, `fs=N=8000` | Bin width 1 Hz; пік 1234 або 1235 Hz (похибка `<=0.5 Hz`); точна амплітуда не вимагалась через leakage |
| TC-09 | 440 Hz; `to_payload`, pickle round-trip | schema v1, source id/rate/samples/spectrum/peaks; periodic Hann; після pickle числові дані, форма й пік збережені |
| TC-10 | Low-pass cutoff = 4000 Hz при `fs=8000` | `ValueError` про межу Найквіста; пакет не створено; вхід незмінний |
| TC-11 | Вхід `[0.0, NaN]` | `ValueError` про finite values; пакет не створено |
| TC-12 | Порожній array | `ValueError` про необхідні аудіокадри; FFT не запускається |

## Checklist з PR3

| ID | Перевірка / очікування |
| --- | --- |
| CL-01 | 440 Hz mono дає FFT bin width 1 Hz при `fs=N=8000` |
| CL-02 | Пік відомого тону — 440 Hz, amplitude `0.8 ± 0.02` |
| CL-03 | Піки 440/1000 Hz упорядковані за амплітудою |
| CL-04 | Low-pass 600 Hz опускає 1000 Hz нижче `0.05` |
| CL-05 | High-pass 700 Hz опускає 440 Hz нижче `0.20` |
| CL-06 | Фільтрація не змінює початковий array |
| CL-07 | Stereo канали з 440/1000 Hz аналізуються незалежно |
| CL-08 | uint8 PCM конвертується у float64, пік 440 Hz amplitude `0.50 ± 0.03` |
| CL-09 | Тиша має нульовий спектр і порожні peaks |
| CL-10 | 1234.5 Hz має похибку піка не більш як 0.5 Hz |
| CL-11 | Packet має schema v1, source id, frames, spectrum, peaks |
| CL-12 | Pickle round-trip зберігає масиви, форму й піки |
| CL-13 | Cutoff `>= fs/2` дає `ValueError` |
| CL-14 | Невідомий тип фільтра дає `ValueError` |
| CL-15 | NaN/Inf відхиляються |
| CL-16 | Порожній масив відхиляється |
| CL-17 | Нульовий/від’ємний sample rate відхиляється |
| CL-18 | Порожній `source_id` відхиляється |

## Кандидати дефектів із PR4 (не підтверджені)

PR4 каже, що модулі ще не були реалізовані на час підготовки, тому кожен опис має статус Not tested і має бути перевірений фактичним запуском.

У вбудованих скриншотах PR4 усі чотири Jira issues MLT-30–33 мають status `To Do` і пов’язані зі Sprint 1. Це підтверджує лише стан карток на момент знімка; фактичні поля звіту окремо вказують `Actual result: Not determined/Not tested`.

| Jira | Сценарій | Пріоритет/тяжкість у звіті | Очікувана поведінка |
| --- | --- | --- | --- |
| MLT-30 | Коректні mono/stereo WAV разом із пошкодженим `broken.wav` | High / S3 Major | Два валідні файли завантажити; помилку пошкодженого відокремити |
| MLT-31 | 0-byte `empty.wav` | Medium / S3 Major | Контрольована помилка без аварії |
| MLT-32 | Синус 440 Hz, `fs=800000`, 800000 samples | High / S3 Major | FFT домінантний пік 440 Hz |
| MLT-33 | 200 Hz amplitude 1.0 + 600 Hz amplitude 0.5, `fs=800000`, 1 s | Medium / S3 Major (попередньо) | Піки у порядку 200, 600 Hz |

Окремий bug-report для MLT-5 також описує як потенційний дефект недостатнє послаблення високої складової low-pass фільтром. Він теж не підтверджений.

## Фактичний аудит MLT-5 — 2026-11-08

Перевірено код із цього checkout коротким inline Python harness у наявному `.venv`; файли тестів у репозиторій не додавалися. `pytest` suite відсутній, тому ці результати — прямі числові перевірки, а не повний автоматизований regression suite.

| Перевірка | Фактичний результат |
| --- | --- |
| PR3 TC-01/02: тони 440/1000 Hz | 440 Hz → amplitude 0.8; суміш повернула 440 Hz/0.8 і 1000 Hz/0.3 у правильному порядку |
| PR3 TC-03/04: low/high-pass | Low-pass 600 Hz: 440 Hz → 0.770514, 1000 Hz → 0.033643. High-pass 700 Hz: 440 Hz → 0.116079, 1000 Hz → 0.293302. Вхідний array не змінився |
| PR3 TC-05/06: stereo та uint8 | Stereo shape `(8000, 2)`, spectrum `(4001, 2)`, канали незалежні; uint8 перетворився у float64, 440 Hz amplitude пройшла `0.50 ± 0.03`; вхід не змінився |
| PR3 TC-07/08: тиша та off-bin tone | Тиша дала нульовий спектр і порожні піки. Сигнал 1234.5 Hz повернув 1235 Hz, похибка рівно 0.5 Hz |
| PR3 TC-09…12: payload/pickle і негативні значення | Pickle зберіг schema/масиви; Nyquist cutoff, NaN і порожній сигнал відхилені очікуваними `ValueError` |
| Jira MLT-32: 800 kHz, 800000 frames | 440 Hz tone повернувся як 440 Hz, amplitude 1.0. Один функціональний прогін тривав близько 0.14 s; це не benchmark і не доказ speedup |
| Jira MLT-33: 800 kHz, 800000 frames, 200 Hz/1.0 + 600 Hz/0.5 | Отримано `(200 Hz, 1.0)`, `(600 Hz, 0.5)` у спадному порядку амплітуди; bin width 1 Hz; очікування Jira пройшли |

### Виправлена помилка відбору піків

До зміни коду (`src/signal_proc/processing.py`) дві комбінації параметрів відтворювали втрачені валідні піки:

- Тон 100 Hz/amplitude 1 поза `min_frequency_hz=500` разом із тоном 1000 Hz/amplitude 0.02 та ratio 5% давав порожній список: threshold помилково спирався на позадіапазонний максимум.
- Тони 500 Hz/1 і 505 Hz/0.5 з межею 503 Hz та `min_separation_hz=10` давали порожній список: SciPy distance спершу відкидав 505 Hz через сильний 500 Hz пік, а нижня межа прибирала 500 Hz.

Виправлено: частотний діапазон тепер задає reference maximum для threshold; фізична мінімальна відстань застосовується лише після формування та фільтрації кандидатів. Обидва сценарії повторно пройшли, повернувши відповідно 1000 Hz/0.02 і 505 Hz/0.5. Синтаксичну компіляцію двох пакетних модулів також перевірено через `.venv/bin/python -m py_compile`.

Жоден Jira Bug не створювався: MLT-32/33 не відтворилися на MLT-5 коді, а запит користувача був лише на аналіз. На момент цього MLT-5 audit MLT-4 WAV reader був відсутній у `main`, тому MLT-30/31 parsing не перевіряли. Окремий branch review виконаний нижче. Історичний low-pass bug-report перевірено критеріями PR3 TC-03; зазначені там attenuation thresholds пройдені.

## Окрема задача: unit suite для `signal_proc` — виконано у визначеному scope

Live Jira MLT-14 (`Створити unit-тести`) має status `To Do`, parent MLT-1 і на момент знімка не був призначений поточному API-акаунту; користувач окремо доручив цю задачу. Опис MLT-14 також згадує WAV parser; тодішній suite обмежено `signal_proc` та його `AudioPacket` boundary. Окремий WAV-reader candidate і його тести на `origin/mlt-4-wav` оцінені нижче.

- Framework: `pytest`; test files розташовані в `test/`, host-only runner — `python3 test/run_tests.py`.
- Assertion forms: стандартний `assert`, `pytest.approx`, `pytest.raises`, `numpy.testing` та mock call assertions.
- Test doubles: `butter_stub` повертає контрольовані SOS sections, а `unittest.mock.Mock` для `sosfilt` перевіряє виклик і віддає заданий вихід. Окремі numeric tests продовжують використовувати справжню SciPy реалізацію.
- Coverage: Coverage.py з branch measurement через `coverage run --branch --source=signal_proc -m pytest test`, далі `coverage report -m`; pytest-cov не потрібен.
- Перед запуском тестовий файл скомпільовано та `pytest --collect-only` підтвердив рівно 10 кейсів. Очікування звірено статично за API, Jira acceptance прикладами та numeric results. На Python 3.13.7/pytest 9.2.0 фактичний результат — 10/10 за 1.97 s.
- Десять кейсів покривають: MLT-32/33 частотну роздільність і порядок піків; stereo канали; реальні low/high-pass фільтри; два test doubles; signed/unsigned PCM; непарний FFT; Nyquist/silence/one-frame; threshold/range/separation/max peaks; валідацію; payload/pickle.
- Попередній 45-кейсовий набір знайшов дефект Nyquist endpoint: для 4 kHz при `fs=8 kHz` два останні Hann bins мали однакову амплітуду, але endpoint не додавався. Виправлено production code (`>` → `>=`); регресія лишилася серед 10 кейсів. Поточний test-file hash до і після запусків збігається.
- Coverage.py 7.17.2 із branch measurement: загалом 97%; `signal_proc/__init__.py` 100%, `processing.py` — 154 statements (4 пропущені) та 56 branches (3 частково покриті). Пропуски: zero-gain window fallback, частотна межа без жодного bin і відхилення in-range піка через separation. Scope — `signal_proc`, не internals `audio_contracts` і не WAV reader.
- Незалежний read-only review оновленого 10-кейсового suite пройшов без blocker/high findings: очікувані числові значення, assertions і обидва test doubles підтверджені. Цей suite сам по собі покриває лише `signal_proc`; WAV reader окремо тестується в candidate branch нижче.
- `test/README.md` описує команди й поточне coverage. `pyproject.toml` містить optional pytest/coverage dependencies та configuration.
- Jira Done не виставлявся під час `signal_proc` задачі; повний acceptance MLT-14 і пов’язаний статус звіряй за live Jira після інтеграції WAV-reader branch.
- Методичні джерела: [pytest assertions and approximate comparisons](https://docs.pytest.org/en/stable/how-to/assert.html), [pytest parametrization](https://docs.pytest.org/en/stable/how-to/parametrize.html), [Python `unittest.mock`](https://docs.python.org/3/library/unittest.mock.html), [Coverage.py quick start and branch coverage](https://coverage.readthedocs.io/en/latest/), [SciPy Hann window](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.windows.hann.html).

## Review remote branch MLT-4 — 2026-11-08

Перевірено `origin/mlt-4-wav` (`0a36a7e` reader, `94e9145` test reduction) проти live Jira issues другого розробника: MLT-4 Epic In Progress; MLT-6/7/8, MLT-26/27, MLT-30/31 — To Do. Jira не змінювали.

- Статичне зіставлення: `WavSource`/`read_wav_batch` реалізують перелік файлів і ordered per-file results (MLT-6); `read_wav_details` дає sample rate, channels, samples, derived duration і WAV-specific bit depth/encoding (MLT-7); `read_wav`/CLI дають single-file read із typed errors (MLT-8/26). `AudioPacket`/`AudioReadError` відповідають чинному `audio_contracts` schema.
- MLT-27 виконано частково: batch продовжується після помилки, але `read_wav_batch` і CLI працюють послідовно. Паралельна обробка з criterion не реалізована цією гілкою; reader сам зазначає, що worker scheduling належить MLT-2.
- MLT-30 test ставить звичайний текстовий файл між двома WAV і перевіряє продовження. Він не створює структурно валідний, але truncated WAV, хоча `docs/MLT4.md` описує такий випадок. MLT-31 перевіряє zero-byte `empty.wav` → `empty_audio`.
- Код і документація заявляють PCM 8/16/24/32 та IEEE float32/64; fixture tests генерують лише PCM16. Static review не виявив певного decoding defect; решта форматів і truncated-WAV test coverage не доведені.
- Проєктний suite: 18 passed за 1.75 s, включно з 8 MLT-4 і 10 MLT-5 pytest cases. Команда з окремого worktree: `PYTHONPATH=src python -m pytest -p no:cacheprovider test`. Перший звичайний запуск теж дав 18 passed, але з cache-permission warning; повтор без cache provider завершився чисто.

Цей попередній огляд був read-only; Jira статуси не переводилися. Після нього `mlt-4-wav` злито в `main` без конфліктів (`85ce596`); після merge повторно пройшли 18/18 tests. MLT-27 batch worker scheduling лишається відкритим.

## Двотермінальний loopback smoke без проєктного glue — 2026-11-08

На прохання користувача перевірено модульний потік через тимчасовий TCP stream, не додаючи файлів/коду до repository:

- FFmpeg згенерував тимчасовий 1 s PCM16 mono WAV, 8000 Hz, чистий тон 440 Hz. FFmpeg sine filter задає amplitude 1/8 ([офіційна документація](https://ffmpeg.org/ffmpeg-filters.html#sine)); отримане `0.12497339495662549` узгоджується з цим.
- Terminal 1 викликав `audio_io.read_wav(path, source_id=...)`, отриманий `AudioPacket` серіалізував стандартним `pickle` у stdout і передав через Ncat connect mode.
- Terminal 2 запустив Ncat listen mode, прочитав той самий pickle зі stdin, викликав `signal_proc.process_signal` і надрукував короткий JSON summary.
- Ncat loopback endpoint був лише `127.0.0.1`; receiver прийняв 16229 bytes. Фактичний output: `source_id=ncat-loopback-440`, 8000 Hz, 8000 frames, 1 channel, 1.0 s, peak 440 Hz, amplitude `0.12497339495662549`.
- Команда повного існуючого suite після merge: `.venv/bin/python -m pytest -p no:cacheprovider test -q` — **18 passed in 4.62s**. Проєктні файли та тести не змінювалися; тимчасовий WAV вилучено після запуску.

Це доводить, що reader packet можна передати між двома локальними процесами й обробити DSP у другому. `pickle`/Ncat тут були одноразовим harness для довіреного loopback smoke, не протоколом продукту: не приймай pickle з недовіреного джерела і не вважай наявною production CLI/API інтеграцію. `python -m audio_io` лишається окремим reader CLI; `process_signal` доступний через Python API. Офіційний [Ncat usage guide](https://nmap.org/ncat/guide/ncat-usage.html) описує listen/connect режими, а [file-transfer guide](https://nmap.org/ncat/guide/ncat-file-transfer.html) — потокове передавання між ними.

## Призупинення, артефакти й ризики

Призупинити тестування, якщо програма не запускається, середовище несправне, немає файлів або блокувальний дефект не дає продовжити. Після виправлення перевірити середовище, повторити невдалий кейс і регресію, зафіксувати фактичний результат.

Плановані артефакти: unit suites (`test_wav_parser.py`, `test_dsp.py`, `test_multiprocessing.py` як назви у звіті), bug reports Jira, performance таблиця/графіки MLT-12, summary report. Їх фактична наявність не підтверджена.

За планом: підготовка 19–22.09.2026; unit 23–27.09; integration 28–30.09; performance 01–02.10; виправлення/regression 02–04.10. Ризики: затримка worker-ів, некоректне завершення процесу, відсутність speedup на малих файлах, брак WAV fixtures, різні версії бібліотек. Це історичні дати, не поточний графік.
