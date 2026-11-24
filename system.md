# Фактичний стан аудіоаналізу у main

Це опис `main@cb32243` від 2026-11-24, не всієї задуманої системи. Реалізовані MLT-4 WAV reader, MLT-5 DSP, MLT-2 supervised worker pool і окреме SQLite-сховище історії. MLT-3 буде вебінтерфейсом і ще не реалізований. HTTP pipeline з `db974ab` залишається скасованим. Джерела: README, `src/`, pyproject та `docs/MLT2.md`; фактичні перевірки — у `testing.md`.

## Пакети Python

- `audio_contracts` (`src/audio_contracts/`) експортує `AudioPacket`, `AudioReadError`, `AudioReadResult`, `FileJob`, `JobError`.
- `audio_io` (`src/audio_io/`) експортує `WavSource`, `WavFile`, `read_wav`, `read_wav_details`, `read_wav_batch` для MLT-4.
- `signal_proc` (`src/signal_proc/`) експортує `FilterConfig`, `PeakConfig`, `SignalPacket`, `SignalSpectrum`, `SpectralPeak`, `process_signal`.
- Distribution у PyPI metadata зветься `mlt-signal-processing`; це не назва Python import package.
- `batch_proc` (`src/batch_proc/`) виконує per-file worker, supervised spawn pool, incremental scheduling і parent aggregation; має CLI `run`/`history`.
- `result_store` (`src/result_store/`) надає `ResultStore` та SQL schema/seed ресурси; вони включені до wheel через package-data.
- Автоматичне setuptools discovery знаходить усі п'ять пакетів.

## `AudioPacket` — decoded input

`AudioPacket(source_id, sample_rate_hz, samples, source_name=None, schema_version=1)` описує один успішно прочитаний source.

- `source_id`: непорожній рядок; унікальність у межах batch забезпечує caller.
- `source_name`: необов’язковий непорожній label; не використовується для join.
- `sample_rate_hz`: positive integer; `bool`, 0 і negative відхиляються.
- `samples`: NumPy-compatible array; `(frames,)` переводиться у `(frames,1)`, дозволено лише непорожню 2D форму після нормалізації.
- Дозволені integer/unsigned/float dtype (`dtype.kind` `i/u/f`); bool/object/complex відхиляються. Усі float мають бути finite.
- Масив робиться C-contiguous; contiguous array не копіюється. Dataclass frozen, але масив не стає read-only: не модифікуй його після створення або передачі worker-у.
- `frame_count`, `channel_count`, `duration_seconds` обчислюються з масиву та sample rate.
- `to_payload()` додає schema/id/rate/derived fields; `samples` лишається NumPy array, тож payload не є чистим JSON.

`AudioReadError(source_id, error_code, message, source_name=None, schema_version=1)` є результатом невдалого WAV читання. `AudioReadResult` — union успішного і невдалого читання. DTO та WAV reader інтегровані в `main`.

## `process_signal` API

Поточна сигнатура:

```python
process_signal(
    packet: AudioPacket,
    *,
    filter_config: FilterConfig | None = None,
    peak_config: PeakConfig | None = None,
) -> SignalPacket
```

Старий прямий виклик з `samples`, sample rate і keyword `source_id` видалений. API тепер примушує використовувати спільну версійну межу. Файл функція не відкриває й не записує.

## Валідація і нормалізація

- `FilterConfig.kind`: тільки `lowpass` або `highpass`; cutoff має бути finite і `>0`; order — додатне ціле число, без bool.
- `PeakConfig.max_peaks`: додатне ціле; amplitude ratio `[0,1]`; min frequency і min separation — finite та невід’ємні.
- `process_signal` приймає лише `AudioPacket` і відповідні конфігурації/`None`.
- Signed integer PCM масштабується діленням на `max + 1`, тому мінімум дорівнює приблизно -1, максимум трохи менший за 1.
- Unsigned PCM центрується навколо `(max + 1) / 2` і нормалізується до приблизного `[-1,1]`.
- Float відтворює свій amplitude scale у float64 без peak normalization.
- Нефінітні числа відхиляються. Вхідний packet array не змінюється; `_as_audio_frames` створює float64 frames.

## Фільтрація

За наявності config будується Butterworth filter у SOS-формі й застосовується `scipy.signal.sosfilt` уздовж осі кадрів окремо на канал. Cutoff має бути строго нижче `sample_rate_hz / 2`; cutoff на/вище Nyquist дає `ValueError`. Це causal filter, тож на початку короткого сигналу можливий transient. Вихідні `samples` у `SignalPacket` — саме відфільтровані кадри.

## FFT і амплітуди

1. Відняти середнє кожного каналу, прибравши DC.
2. Застосувати periodic Hann (`sym=False`), щоб зменшити spectral leakage.
3. Виконати `scipy.fft.rfft` уздовж кадрів.
4. Нормалізувати модуль FFT на суму вікна; interior bins помножити на 2 для one-sided peak amplitude. Для парної довжини не подвоювати DC/Nyquist, для непарної — DC.
5. Частоти — `rfftfreq(N, 1/fs)`, resolution/bin width — `fs/N`.

Для одного кадру SciPy periodic Hann має одиничне значення, тому після mean removal спектр дорівнює нулю. Код має fallback на одиничне вікно, якщо сума вікна дорівнює нулю; у перевірці прийнятних непорожніх довжин цей fallback не спрацьовує.

## Піки

- Кожен канал аналізується незалежно.
- DC-bin примусово нульовий і не повертається.
- `find_peaks` відбирає локальні максимуми без попереднього обмеження відстані; Nyquist endpoint додається окремо, якщо він не нижчий від попереднього bin, бо periodic Hann може утворити рівний крайовий plateau.
- Спершу застосовується `min_frequency_hz`; відносний amplitude threshold обчислюється від найбільшого bin у дозволеному частотному діапазоні. Далі кандидати сортуються за амплітудою й застосовується `min_separation_hz` у Hz. Піки поза вибраним діапазоном не можуть приховати піки всередині нього.
- Сортування: спадання амплітуди, при однаковій — зростання частоти; повертається не більш як `max_peaks`.
- За замовчуванням: максимум 5 піків, поріг 5%, DC відсутній.
- Пік обмежений FFT-сіткою; окремої parabolic/inter-bin interpolation реалізація не виконує.

Аудит 2026-11-08 виявив і виправив дві помилки: позадіапазонні піки могли впливати на threshold/separation, а Nyquist endpoint губився, коли periodic Hann дав однакові амплітуди в останніх двох бінах. Регресії цих випадків перевіряються в `test/test_signal_proc.py`; попередні inline відтворення та новий pytest suite описані в `testing.md`.

## `SignalPacket` вихід

`SignalPacket` schema v1 містить:

- `source_id`, optional `source_name`, `sample_rate_hz`;
- `samples`: float64 `(frames, channels)` без фільтра або після фільтра;
- `spectrum`: частоти, amplitudes `(frequency_bins, channels)`, bin width, window, DC-removal та amplitude scale;
- `peaks_by_channel`: tuples піків, кожен пік включає channel index, частоту й амплітуду;
- filter/peak config і derived frame/channel/duration properties.

Dataclass та ndarray pickle-compatible для process queue. `to_payload()` є shallow mapping; JSON adapter має окремо вирішити, як зберігати/посилати великі масиви. SignalPacket повертає той самий source identity, щоб aggregator з’єднав результат із правильним файлом при out-of-order worker completion.

## MLT-4 WAV reader у `main`

Гілка `mlt-4-wav` злита в `main` merge commit `85ce596`. Модуль `src/audio_io/` містить `WavSource`, `WavFile`, `read_wav_details`, `read_wav` і `read_wav_batch`. Reader перевіряє RIFF/WAVE chunk bounds, format fields, frame alignment і довжину, декодує через `scipy.io.wavfile.read`, звіряє результат із header metadata та повертає `AudioPacket` або per-file `AudioReadError`. `read_wav_details` додатково повертає bit depth та encoding. Заявлена підтримка — PCM 8/16/24/32 і IEEE float 32/64; автоматичні fixture tests перевіряють лише PCM16.

Batch API зберігає input order і продовжується після file error, але працює послідовно. `python -m audio_io` — CLI огляд reader-а, не MLT-3 UI.

## Межі та відомі обмеження

- MLT-5 не читає WAV, не показує графіки, не запускає worker pool, не пише аудіофайли.
- `main` має MLT-2/4/5 та SQLite history, але не має MLT-3 web UI. HTTP pipeline, який тимчасово додавався, скасований. Див. `architecture.md` і `status.md`.
- Schema v1 і API описують наявний пакетний контракт. Будь-які модифікації мають бути узгоджені в `data_contract.md` і у всіх споживачів.

## MLT-2 та історія — 2026-11-24

`batch_proc` використовує explicit `spawn`, приватний duplex Pipe на worker і максимум один assigned descriptor на процес. Reader та DSP працюють локально у worker, parent отримує `JobResult`. `iter_batch` поступово повертає outcomes, `run_batch` явно накопичує їх у `BatchResult`; API/інваріанти — в `data_contract.md`. Падіння одного worker повертає один `worker_exited`, файл автоматично не повторюється, лише загиблий slot замінюється за потреби pending задач. Ізоляція реального `os._exit(23)`, idle death і cleanup перевірена незалежно. Живий, але завислий worker без watchdog timeout не покривається цією поведінкою.

`ResultStore(path, *, artifact_dir=None)` потребує SQLite >=3.37 із JSON-функціями; кожне connection вмикає й перевіряє FK, зберігає owner PID. Schema user_version=1; непідтримувана версія або чужа непорожня unversioned БД відхиляються. Нормальна ініціалізація не завантажує seed.

API: `create_run(expected_count, worker_count, filter_config, peak_config)`, `save_result(run_id, JobResult)`, `finish_run(run_id, error_message=None)`, `get_run`, `list_runs`, `list_results`, `load_result(result_id)`. Tables — `analysis_run → file_result → spectral_peak`; типи/статуси описані в `data_contract.md`, точний DDL — `src/result_store/schema.sql`.

Успішні результати зберігають повні масиви та spectrum metadata у managed NPZ, без pickle; filter/peak configs і peaks — у SQL. Імена NPZ генеруються випадково, load перевіряє containment у artifact directory. Source WAV для повторного читання історії не потрібний. Збереження result+peaks — одна `BEGIN IMMEDIATE` транзакція, при SQL failure новий NPZ прибирається. SQLite й файлова система не є спільною транзакцією: загибель parent між NPZ та commit може лишити orphan; direct SQL cascade не видаляє зовнішні NPZ, maintenance API відсутній. Для backup/перенесення потрібні БД та sibling `<database-filename>.artifacts/` після завершення запису.

CLI: `python -m batch_proc run --db history.sqlite3 --workers 2 a.wav bad.wav b.wav`; `history --db ... [--run-id ID]`. Run streaming, DB writer тільки parent; exit0 усі успіхи, exit1 файлові помилки після всього batch, exit2 arguments/infrastructure/storage, exit130 interrupt. Storage failure видима й за можливості позначає run failed. Demo: `python examples/batch_demo.py`. Native SQL stored procedures у SQLite відсутні й не заявляються.
