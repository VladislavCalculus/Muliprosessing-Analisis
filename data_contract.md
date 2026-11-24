# Контракт даних між модулями

## Призначення

MLT-4 читає WAV, MLT-5 обробляє декодовані відліки. Їхній контракт має дозволяти окреме тестування модулів, кореляцію результатів із джерелом і контрольоване продовження пакетної роботи після помилки одного файла.

Реалізований контракт — Python dataclass + NumPy array у `src/audio_contracts/`. Він призначений для модулів цього Python-проєкту. Це не файловий формат і не зовнішній HTTP-протокол.

## Успішне читання: `AudioPacket` schema 1

Один успішно декодований файл утворює рівно один `AudioPacket`:

| Поле | Тип / інваріант | Призначення |
| --- | --- | --- |
| `schema_version` | `int`, наразі тільки `1` | Версія структури та правил семплів |
| `source_id` | Непорожній `str`, унікальний у межах одного batch | Кореляція події, помилки й результату |
| `source_name` | `str | None` | Коротка назва для UI; не використовується як ідентифікатор |
| `sample_rate_hz` | Додатне ціле число | Частота дискретизації в Hz |
| `samples` | NumPy-масив `(frames, channels)`, C-contiguous, dtype integer або float | Декодовані значення без копіювання WAV-файла |

Додаткові похідні властивості:

- `frame_count = samples.shape[0]`;
- `channel_count = samples.shape[1]`;
- `duration_seconds = frame_count / sample_rate_hz`.

Їх не передають окремими конструкторними полями, щоб вони не розходилися з реальною формою масиву. Для mono читач може передати `(frames,)`; пакет канонізує її до `(frames, 1)`. Порожня форма та нуль каналів не допускаються.

### Правила значень семплів

- Integer PCM передається у вихідному числовому масштабі й типі (`int16`, `int32`, `uint8` тощо). `signal_proc` нормалізує його до `float64` приблизно в `[-1, 1]`.
- Float WAV передається зі своїм масштабом; його не треба нормалізувати до одиниці автоматично.
- Bool, object, complex та інші неаудіо типи відхиляються. Float `NaN`/`Inf` відхиляються.
- Масив приводиться до C-contiguous, але вже contiguous масив не копіюється. Зовнішній dataclass frozen; NumPy-масив технічно все ще змінюваний, тому виробник має вважати його immutable після створення/передачі пакета.

### Ідентичність джерела

`source_id` має створювати клієнт/оркестратор до читання й залишатися незмінним у всьому циклі. Він мусить розрізняти два файли з однаковою назвою. `source_name` призначений для відображення. Пакет не зберігає відкритий файловий об’єкт чи залежність від WAV-парсера.

## Помилка читання: `AudioReadError`

Якщо файл порожній, пошкоджений, не підтримується або не читається, MLT-4 формує `AudioReadError`, а не частково заповнений `AudioPacket`:

| Поле | Тип / правило |
| --- | --- |
| `schema_version` | `1` |
| `source_id` | Той самий ідентифікатор завдання |
| `source_name` | Необов’язкова коротка назва файла |
| `error_code` | Непорожній стабільний машинний код |
| `message` | Коротке повідомлення для журналу/UI; не є API-кодом |

Рекомендовані коди: `unsupported_format`, `invalid_wav`, `empty_audio`, `read_failed`. Список можна розширювати без зміни значення наявних кодів. Не передавай між процесами об’єкт Python exception, traceback або відкритий файл.

`AudioReadResult = AudioPacket | AudioReadError` — результат одного читання. Оркестратор позначає невдалий `source_id`, повідомляє UI та переходить до наступного файла. `signal_proc.process_signal` приймає тільки `AudioPacket`.

## Контракт MLT-5

Виклик: `process_signal(packet, *, filter_config=None, peak_config=None)`. Він:

1. перевіряє тип `AudioPacket` і конфігурації;
2. перетворює integer PCM у `float64`, float залишає в його амплітудному масштабі;
3. за потреби фільтрує кадри;
4. формує спектр і незалежні списки піків на канал;
5. повертає `SignalPacket` schema 1 з тим самим `source_id` та `source_name`.

`SignalPacket` містить оброблені `samples`, `sample_rate_hz`, спектр, піки, параметри фільтра/піків і похідні властивості. `to_payload()` — shallow mapping: великі NumPy-масиви залишаються масивами. Вихідний WAV не перезаписується.

Невалідний cutoff/config або некоректні семпли є помилкою одного завдання: майбутній worker wrapper має зловити її на межі файла та повернути помилку з тим самим `source_id`; не маскуй її порожнім `SignalPacket`.

## Передавання між процесами

### Рішення для MLT-4 → MLT-5

`AudioPacket` — контракт модулів. Якщо читання й DSP виконуються в одному worker-і, передавай об’єкт напряму в `process_signal`; серіалізація не потрібна.

### Рішення для MLT-2 черг

За замовчуванням не став у process queue великий `AudioPacket`. Для системи, що обробляє WAV-файли з локального диска, parent має надсилати worker-ам легке завдання з `source_id`, шляхом і назвою; worker виконує MLT-4, створює `AudioPacket` і відразу викликає MLT-5. Це прибирає pickle/copy великого масиву на вході worker-а.

Якщо середовище змушує парсер працювати в parent-процесі, передавай dataclass через `multiprocessing.Queue`/pickle, а не JSON/base64. Це простий перший варіант, але NumPy-масив серіалізується за значенням і може подвоїти витрати пам’яті/часу. Для великих файлів виміряй це; лише після виміру переходь на `multiprocessing.shared_memory` із малим descriptor (name, dtype, shape, metadata) і окремим протоколом звільнення пам’яті.

На виході worker-а `SignalPacket` також може містити великі масиви. Спочатку повертай його стандартною чергою; якщо заміри покажуть bottleneck, оптимізуй окремо. Не вводь shared memory наперед.

## Версіонування

- Чинна схема входу — `AudioPacket` v1; чинна схема DSP-виходу — `SignalPacket` v1.
- Не змінюй значення існуючого поля або одиницю виміру в тій самій версії.
- Нове необов’язкове поле можна додати сумісно лише після перевірки всіх споживачів і з default, який підтримує старий payload.
- Несумісна зміна форми/типу/значення — нова schema version; читач має явно відхилити невідому версію.
- `to_payload()` потрібен для адаптерів/логування, але не визначає окремий JSON-протокол для масивів.

## Наявна реалізація проти майбутнього

`AudioPacket`, `AudioReadError`, `AudioReadResult`, WAV parser і прийом пакета в MLT-5 реалізовані. У реалізації від 2026-11-24 додано наведені нижче descriptor, per-file outcome та process pool. Web UI/MLT-3 лишається майбутнім модулем. Loopback HTTP pipeline, що тимчасово був у `db974ab`, скасований; він не є чинним контрактом.

## MLT-2: завдання та результат — 2026-11-24

Підтверджено `src/audio_contracts/jobs.py`, `src/batch_proc/{worker,pool,schedule,batch}.py` та незалежними перевірками кожного Jira milestone. Це доповнення без зміни `AudioPacket`/`SignalPacket` v1.

| Тип | Поля та правила |
| --- | --- |
| `audio_contracts.FileJob` | Frozen/slotted dataclass: непорожній `source_id`, `path` (text path-like, нормалізований до абсолютного `Path`), `source_name: str\|None`, `schema_version=1`. Немає ndarray; шлях може ще не існувати — це read error worker-а. |
| `audio_contracts.JobError` | Frozen/slotted: `source_id`, непорожні `error_code`/`message`, `stage` = `read`/`process`/`worker`, optional `source_name`, `schema_version=1`. Exception/traceback не передаються. |
| `batch_proc.JobResult` | `job: FileJob`, рівно одне з `packet: SignalPacket\|None` / `error: JobError\|None`, додатний integer `worker_pid`, finite nonnegative `elapsed_seconds`. `source_id` payload має збігатися з job. Окремого поля schema version у wrapper немає. Властивості `source_id`, `succeeded`. |
| `batch_proc.BatchResult` | `results_by_source: dict[str,JobResult]`, узгоджений `total_count`, `parent_pid`, `elapsed_seconds`; похідні `success_count`, `failure_count`, `worker_pids`. Wrapper frozen, dict/NumPy arrays shallow mutable; не змінювати під час передавання споживачам. |

`process_file(job, *, filter_config=None, peak_config=None)` читає WAV та виконує DSP в одному поточному процесі. Caller type errors відхиляються до читання. Звичайна read failure зберігає код reader-а; звичайний DSP exception стає `processing_failed` зі stage `process`.

`iter_batch(jobs, *, worker_count=2, filter_config=None, peak_config=None)` перевіряє скінченний набір легких descriptor-ів і унікальність ID до spawn. Пул має не більше `min(worker_count, job_count)` reusable spawn-процесів. Parent тримає pending deque, кожен worker має приватний duplex Pipe та не більше одного assigned job. Вхідний `AudioPacket` через IPC не йде; вихідний `JobResult` серіалізує повні масиви стандартним pickle.

Ітератор повертає результати за завершенням, не за вхідним порядком. Споживати через `source_id`, при достроковому виході закрити ітератор (`contextlib.closing`). `run_batch(..., on_result=None)` — явний opt-in збір усіх packet-ів у RAM; callback працює синхронно в parent. Його помилка видима викликачеві після очищення пулу.

Аварія assigned worker дає один `worker_exited` outcome зі stage `worker`. Аварійний файл не повторюється автоматично; лише загиблий slot замінюється за потреби наступних задач, surviving worker продовжує роботу. При загибелі idle процесу незапущений descriptor зберігається. Загальна кількість replacements обмежена, інфраструктурна неможливість продовження піднімає явний exception. Це не watchdog для живого, але завислого обчислення.

Фактичний розмір pickle для 1 s mono/8000 Hz/8000 frames/440 Hz: `FileJob` **192 bytes**, `JobResult` **129039 bytes**, пік 440 Hz. Доказ — `docs/database_testing/ipc-size.json`. Це вимір розміру одного payload, не throughput/speedup benchmark і не доказ відсутності bottleneck для великих WAV.

## SQLite history schema 1 — 2026-11-24

Точний DDL — `src/result_store/schema.sql`, standalone SQL fixture — `seed.sql`; файли включені до distribution. Кожне connection має FK=ON. `STRICT` таблиці потребують SQLite >=3.37, JSON configs перевіряються `json_valid`.

| Таблиця | Контракт та інваріанти |
| --- | --- |
| `analysis_run` | Текстовий непорожній run_id (API генерує UUID hex), UTC created/finished timestamps, `status=running/completed/failed`, nonnegative integer expected_count, positive worker_count/parent_pid, nullable filter_json і required peak_json. Параметри після створення не змінюються; finish тільки один раз. Completed потребує рівно expected_count outcomes і може містити файлові помилки. Failed означає інфраструктурне переривання з error_message та можливими частковими результатами. |
| `file_result` | Integer result_id, FK run_id ON DELETE CASCADE, source_id/path/name, status succeeded/failed, worker_pid та finite elapsed_seconds. UNIQUE(run_id,source_id). Success має positive sample_rate_hz/frame_count/channel_count і managed artifact_name, без error fields. Failure має stage/code/message, без sample metadata/NPZ; метадані невдалого читання не вигадуються. UPDATE заборонено trigger-ом. |
| `spectral_peak` | Integer peak_id, FK result_id ON DELETE CASCADE, nonnegative channel_index/peak_index, positive finite frequency_hz/amplitude, UNIQUE(result_id,channel_index,peak_index). Trigger допускає лише successful parent, канал < channel_count, frequency <= sample_rate_hz/2 та running run. Амплітуда може перевищувати 1, бо float audio не нормалізується за peak. UPDATE заборонено. |

`run_summary` — SQL view: completed/success/failure counts та wall-clock duration_seconds через count/sum/coalesce/julianday/round. Запис після завершення запуску/понад expected_count відхиляється. Це два FK master–detail зв'язки; повторне використання source_id в іншому run дозволене.

`save_result` приймає підтримуваний SignalPacket schema1 з конфігураціями, що збігаються з run. Один result і всі його peaks записуються атомарно; scalar bounds перевіряє SQL, числові ndarray також перевіряються на finite перед NPZ. `load_result` повертає повний JobResult з source identity/configs/масивами/піками; JSON-safe list/get API містить metadata й peaks, а не великі ndarray. Артефакти, seed-обмеження та crash consistency — у `system.md`/`docs/MLT2.md`.

Seed — лише SQL metadata fixture: 1 run, 2 file outcomes (success/error), 2 peaks. `seed-tone.npz` — явно ілюстративне посилання; фізичного NPZ seed не створює й числовий load цього запису не обіцяється. Реальний round-trip перевірено через ResultStore/CLI.
