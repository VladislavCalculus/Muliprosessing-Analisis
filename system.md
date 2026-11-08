# Фактичний стан MLT-5 та shared contract

Це опис поточного коду, не всієї задуманої системи. У цьому repository реалізований MLT-5 та його контракт із майбутнім MLT-4. Джерела: [`../README.md`](../README.md), [`../src/signal_proc/processing.py`](../src/signal_proc/processing.py), [`../src/audio_contracts/packets.py`](../src/audio_contracts/packets.py), [`../pyproject.toml`](../pyproject.toml).

## Пакети Python

- `audio_contracts` (`src/audio_contracts/`) експортує `AudioPacket`, `AudioReadError`, `AudioReadResult`.
- `signal_proc` (`src/signal_proc/`) експортує `FilterConfig`, `PeakConfig`, `SignalPacket`, `SignalSpectrum`, `SpectralPeak`, `process_signal`.
- Distribution у PyPI metadata зветься `mlt-signal-processing`; це не назва Python import package.
- Автоматичне setuptools discovery має знаходити тільки `audio_contracts` та `signal_proc`.

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

`AudioReadError(source_id, error_code, message, source_name=None, schema_version=1)` є результатом невдалого WAV читання. `AudioReadResult` — union успішного і невдалого читання. Це DTO є в коді; реальний модуль MLT-4 поки відсутній.

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

Однокадрове вікно Hann має нульову суму; код у цьому випадку використовує одиничне вікно як fallback.

## Піки

- Кожен канал аналізується незалежно.
- DC-bin примусово нульовий і не повертається.
- `find_peaks` відбирає локальні максимуми без попереднього обмеження відстані; Nyquist bin додається окремо, якщо він більший за попередній bin.
- Спершу застосовується `min_frequency_hz`; відносний amplitude threshold обчислюється від найбільшого bin у дозволеному частотному діапазоні. Далі кандидати сортуються за амплітудою й застосовується `min_separation_hz` у Hz. Піки поза вибраним діапазоном не можуть приховати піки всередині нього.
- Сортування: спадання амплітуди, при однаковій — зростання частоти; повертається не більш як `max_peaks`.
- За замовчуванням: максимум 5 піків, поріг 5%, DC відсутній.
- Пік обмежений FFT-сіткою; окремої parabolic/inter-bin interpolation реалізація не виконує.

Аудит 2026-11-08 виявив і виправив помилку попереднього порядку відбору: відносний поріг брав максимум із усього спектра, а `find_peaks(distance=...)` міг видалити слабший пік до застосування нижньої частотної межі. Регресійні сигнали з сильним 100 Hz піком і слабким 1000 Hz піком, а також 500/505 Hz при межі 503 Hz, після виправлення повертають відповідний in-range пік. Результати — у `testing.md`.

## `SignalPacket` вихід

`SignalPacket` schema v1 містить:

- `source_id`, optional `source_name`, `sample_rate_hz`;
- `samples`: float64 `(frames, channels)` без фільтра або після фільтра;
- `spectrum`: частоти, amplitudes `(frequency_bins, channels)`, bin width, window, DC-removal та amplitude scale;
- `peaks_by_channel`: tuples піків, кожен пік включає channel index, частоту й амплітуду;
- filter/peak config і derived frame/channel/duration properties.

Dataclass та ndarray pickle-compatible для process queue. `to_payload()` є shallow mapping; JSON adapter має окремо вирішити, як зберігати/посилати великі масиви. SignalPacket повертає той самий source identity, щоб aggregator з’єднав результат із правильним файлом при out-of-order worker completion.

## Межі та відомі обмеження

- MLT-5 не читає WAV, не показує графіки, не запускає worker pool, не пише аудіофайли.
- Основний продукт у поточному checkout не має коду MLT-4/2/3; див. `architecture.md` і `status.md`.
- Schema v1 і API описують наявний пакетний контракт. Будь-які модифікації мають бути узгоджені в `data_contract.md` і у всіх споживачів.
