# MLT-2: межі багатопроцесної обробки

MLT-21 визначає межу завдання й результату. MLT-22 додає керований пул
повторно використовуваних worker-процесів, MLT-19 — розподіл batch.
MLT-20 збирає результати в parent, MLT-29 ізолює аварію worker-а;
окремий `result_store` зберігає історію SQLite, CLI доступний без UI.

## Хто виконує роботу

- Головний процес створює `audio_contracts.FileJob` для кожного вибраного WAV.
  `source_id` має бути унікальним у межах запуску, незалежно від імені файла.
- У worker-процес передається легкий descriptor: `source_id`, абсолютний шлях,
  необов'язкова назва та `schema_version=1`. Декодованого ndarray у ньому немає.
- `batch_proc.process_file` виконує `audio_io.read_wav` і
  `signal_proc.process_signal` послідовно в тому самому процесі. Межа
  MLT-4 → MLT-5 лишається чинним `AudioPacket` v1 без IPC.
- Результат `JobResult` містить вихідний descriptor, рівно один `SignalPacket`
  або `JobError`, PID worker-а та час читання/обробки в секундах. Для аварії
  worker-а час вимірює parent від призначення descriptor-а до виявлення збою.

Обмін пулу: parent надсилає не більше одного активного `FileJob`
кожному worker-у через його IPC pipe; черга descriptor-ів залишається в parent.
Повернення `JobResult` стандартно серіалізує NumPy-масиви вихідного пакета.
На вході масиви не копіюються між процесами. Shared memory не додається без
вимірювання потреби. Великі результати потрібно споживати поступово, а не
накопичувати необмежено.

## Помилки й інваріанти

`JobError` — невеликий pickle-сумісний dataclass із `source_id`, `error_code`,
`message`, `stage`, `source_name` та `schema_version=1`. Для помилки читання
зберігаються машинний код і повідомлення `AudioReadError`; stage дорівнює
`read`. Звичайний виняток DSP повертає `processing_failed` зі stage `process`.
Stage `worker` використовується для помилок, які supervisor виявляє
поза завершеною функцією, зокрема аварійного завершення процесу.

Виконавець не передає exception, traceback чи відкриті файли між процесами.
Некоректні типи API-аргументів відхиляються до читання; помилка конкретного
файла повертається як результат і не заважає наступному виклику.
`JobResult` перевіряє відповідність `source_id` вихідного пакета descriptor-у.

## Приклад для одного файла

```python
from audio_contracts import FileJob
from batch_proc import process_file
from signal_proc import FilterConfig

result = process_file(
    FileJob("selection-1", "example.wav"),
    filter_config=FilterConfig("lowpass", 600),
)
if result.succeeded:
    print(result.packet.peaks_by_channel)
else:
    print(result.error.stage, result.error.error_code, result.error.message)
```

Цей виклик працює в поточному процесі. Сам по собі він не запускає pool і
не виконує критерій паралельності MLT-29. Чинні `AudioPacket`, `SignalPacket`,
`read_wav` і `process_signal` не змінені.

## Життєвий цикл пулу MLT-22

`WorkerPool(worker_count, *, filter_config=None, peak_config=None)` явно
використовує multiprocessing context `spawn`. Функції worker-ів і DTO
визначені на рівні модулів. Виклик створення процесів у скрипті потрібно
захищати `if __name__ == "__main__":`.

```python
from audio_contracts import FileJob
from batch_proc import WorkerPool

if __name__ == "__main__":
    with WorkerPool(2) as pool:
        pool.submit(FileJob("first", "first.wav"))
        pool.submit(FileJob("second", "second.wav"))
        while pool.active_count:
            result = pool.receive()
            print(result.source_id, result.succeeded)
```

`submit` повертає номер worker-а й відхиляє перевищення кількості активних
завдань; `receive(timeout)` повертає один результат або `None` після timeout.
Після отримання результату той самий worker приймає наступний файл.
`worker_pids`, `idle_worker_ids`, `active_count` дозволяють supervisor-у
відстежувати реальний стан пулу. Виклики належать одному parent-thread.

Контекст закриває IPC та завершує всі процеси навіть при винятку викликачa;
незавершені завдання при закритті перериваються. Звичайне завершення idle
worker-ів має обмежений grace period, після нього застосовується terminate/kill.
Помилка часткового запуску також прибирає вже створені процеси.
`WorkerExitedError` на низькорівневому API повідомляє номер/PID worker-а,
descriptor активного завдання та exitcode, якщо процес вийшов без повного
результату. `iter_batch` обробляє цю подію відповідно до MLT-29.

## Розподіл файлів MLT-19

`iter_batch(jobs, *, worker_count=2, filter_config=None, peak_config=None)`
приймає скінченний iterable `FileJob` і видає `JobResult` у порядку завершення.
Перед запуском першого процесу перевіряються типи всіх descriptor-ів та
унікальність `source_id`; запам'ятовуються тільки легкі descriptor-и.
Порожній batch не запускає процесів і не читає файлів.

Кількість worker-ів обмежена `worker_count` та кількістю завдань. На кожен
worker припадає не більше одного активного файла. Після отримання результату
вільний worker отримує наступний descriptor. Звичайна помилка читання/DSP
повертається як результат цього файла, решта pending-файлів продовжується.
Порядок завершення не можна використовувати для зіставлення зі списком
вхідних файлів — використовується `source_id`.

```python
from audio_contracts import FileJob
from batch_proc import iter_batch

if __name__ == "__main__":
    jobs = [FileJob("one", "one.wav"), FileJob("two", "two.wav")]
    for result in iter_batch(jobs, worker_count=2):
        print(result.source_id, result.succeeded)
```

Ітератор не збирає всі `SignalPacket` у список. Якщо викликач припиняє
ітерацію достроково, потрібно викликати `close()` або використати
`contextlib.closing`: тоді context пулу завершить зайняті процеси.
Аварію процесу перетворено на один корельований `JobResult` зі stage `worker`.

## Збір результатів MLT-20

`run_batch` приймає ті самі параметри, що `iter_batch`, і повертає
`BatchResult`: `results_by_source`, `total_count`, `parent_pid`,
`elapsed_seconds`; властивості `success_count`, `failure_count`, `worker_pids`.
Словник містить повні `JobResult` з відфільтрованими кадрами, спектром,
per-channel піками або помилкою. Результати зіставляються за `source_id`,
незалежно від завершення worker-ів. Порожній запуск має нульові лічильники.

Це opt-in агрегатор: він утримує **всі** масиви batch у пам'яті.
Для великих WAV використовуйте `iter_batch` і споживайте результати поступово.
Масиви та словник у `BatchResult` технічно змінювані — не змінюйте їх під час
передачі наступним споживачам.

Необов'язковий `on_result(result)` викликається синхронно в головному процесі
після отримання кожного результату. Це точка підключення збереження або
події «файл завершено»; вона не імітує CPU utilization чи точний прогрес DSP.
Виняток callback-а передається викликачеві після cleanup пулу. Отже, збій
майбутнього сховища не маскується під успішну обробку або помилку WAV.

## Ізоляція аварії worker-а MLT-29

Parent очікує готові Pipe або process sentinel. Якщо worker завершився без
повного результату, його призначений файл отримує `worker_exited`. Цей файл
не запускається повторно автоматично. Інші worker-и та їхні активні задачі
залишаються недоторканими. Якщо є pending-файли, створюється заміна лише
загиблому процесу; без pending-файлів він просто прибирається.

Якщо процес загинув idle до призначення descriptor-а, цей descriptor лишається
в parent-черзі й передається справному worker-у. Кількість замін на batch
обмежена `кількість файлів + worker_count`; перевищення — видима помилка
інфраструктури з cleanup, без нескінченного циклу запуску.
Незавершені кадри IPC не інтерпретуються як успішний пакет.

Відновлення не означає автоматичне продовження завислого живого процесу:
окремий per-file watchdog timeout зараз не визначений. Скасування ітератора
або виняток callback-а закриває pool та завершує зайняті worker-и.
Fault-injection використовується тільки приватним seam у тестах; користувацьких
CLI прапорців для аварійного завершення немає.

## SQLite-сховище

`result_store.ResultStore` володіє одним connection у процесі й thread,
що його створили. Workers не отримують connection і не записують до БД.
Потрібна SQLite 3.37+ (`STRICT` tables) із JSON-функціями; підтримка явно
перевіряється. У кожному connection увімкнено `PRAGMA foreign_keys=ON`.
Невідома schema version або непорожня unversioned БД відхиляється.

Схема v1 містить три таблиці:

| Таблиця | Призначення |
| --- | --- |
| `analysis_run` | Час, очікувана кількість файлів, workers, parent PID, параметри фільтра/піків, стан запуску |
| `file_result` | FK на запуск, унікальний у запуску `source_id`, шлях/назви, статус, PID/час worker-а, метадані або помилка |
| `spectral_peak` | FK на результат, канал, індекс у впорядкованому списку, частота Hz та амплітуда |

Файл із read/process/worker error не отримує вигаданих sample rate,
кількості кадрів/каналів чи піків. Для успішного результату вони обов'язкові.
Амплітуда піка додатна й скінченна, але **не** обмежена одиницею: float WAV
зберігає власний масштаб. Частота не перевищує Найквіст, канал належить
файлу. `UNIQUE(run_id,source_id)` забезпечує кореляцію.

Тригери дозволяють додавати результати тільки до running-запуску й не більше
очікуваної кількості; перевіряють піки та забороняють переписування збережених
результатів/піків. Так parent-метадані не можуть стати несумісними з дочірніми
піками. Запуск можна завершити один раз; completed вимагає всі результати.
Окремі file errors не роблять запуск інфраструктурно failed: він completed
із ненульовим failure_count. Failed означає переривання всієї обробки/збереження.

`run_summary` — SQL view з лічильниками та нативними `julianday`, `coalesce`,
`round`. Метадані конфігурацій перевіряються `json_valid`. Власних Python UDF
для створення чи заповнення БД немає. SQLite не має стандартних збережених
процедур; Python-методи сховища не видаються за SQL stored procedures.

```python
from result_store import ResultStore
from batch_proc import iter_batch, validate_jobs
from audio_contracts import FileJob
from contextlib import closing

if __name__ == "__main__":
    jobs = validate_jobs([FileJob("one", "one.wav"), FileJob("two", "two.wav")])
    with ResultStore("history.sqlite3") as store:
        run_id = store.create_run(expected_count=len(jobs), worker_count=2)
        with closing(iter_batch(jobs, worker_count=2)) as results:
            for result in results:
                store.save_result(run_id, result)
        store.finish_run(run_id)
        print(store.get_run(run_id))
```

API: `create_run` повертає run ID; `save_result` — result ID; `finish_run`
завершує запуск або, з `error_message=...`, позначає інфраструктурну невдачу.
`list_runs`, `get_run`, `list_results` повертають JSON-сумісні метадані;
`load_result(result_id)` відновлює повний `JobResult` разом із масивами й піками.
Версії packet, відмінні від v1, та невідповідність конфігурації запуску
відхиляються. Час worker outcome для звичайної обробки та аварії має межі,
зазначені вище; SQL duration запуску — wall-clock різниця timestamps, не
benchmark прискорення.

### SQL і числові артефакти

`src/result_store/schema.sql` виконується самостійно стандартним sqlite3;
`seed.sql` — окремий мінімальний навчальний fixture (1 запуск, 2 файли,
2 піки), який нормальна ініціалізація **не** завантажує:

```sh
sqlite3 /tmp/seed-history.sqlite3 < src/result_store/schema.sql
sqlite3 /tmp/seed-history.sqlite3 < src/result_store/seed.sql
```

Seed містить лише SQL-метадані: `seed-tone.npz` є ілюстративним посиланням,
реального NPZ у ньому немає. Для повного числового round-trip використовуйте
реальний `save_result` або демонстрацію CLI. SQL ресурси включені до wheel.

Успішний результат записується у випадково названий NPZ без pickle:
відфільтровані кадри, частоти/амплітуди спектра та його метадані.
БД зберігає відносну назву NPZ, за замовчуванням у каталозі
`<database-filename>.artifacts/`. Один file-result і всі його піки — одна SQL
транзакція; у разі помилки SQL створений NPZ прибирається, рядки відкочуються.
Якщо весь процес загине між створенням NPZ та commit, можливий orphan-файл:
повної транзакційності файлової системи й SQLite разом не заявлено.

Для backup або перенесення потрібно зберігати БД і каталог артефактів разом
після завершення запису. Можна задати `artifact_dir=...` у API й передати
його знову при відкритті. Пряме SQL-видалення запуску каскадно видаляє
метадані й піки, але не зовнішні NPZ; автоматичне очищення orphan-файлів
окремим maintenance API не реалізовано. Користувацьких API редагування
результатів чи видалення історії наразі немає.

### CLI

`python -m batch_proc run --db history.sqlite3 --workers 2 a.wav bad.wav b.wav`
виконує streaming batch із записом parent-ом; результатами не заповнюється
необмежений in-memory список. `history --db ...` показує запуски, а
`history --db ... --run-id ID` — результати одного запуску й піки без повторного DSP.
Параметри фільтра: `--filter lowpass|highpass --cutoff-hz HZ --order N`;
пошук піків: `--max-peaks N`. `--filter` і `--cutoff-hz` задаються разом.
Наявна історія не перезаписується. Виняток сховища завершує pool, передається
користувачу й за можливості позначає запуск failed. Перерваний до finish
процес може лишити running-запуск; автоматичне crash-recovery таких запусків
ще не визначено.
