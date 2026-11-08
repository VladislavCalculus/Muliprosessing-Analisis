# MLT: читання WAV та цифрова обробка сигналів

У проєкті є два незалежні модулі: `audio_io` (MLT-4) читає WAV-файли,
а `signal_proc` (MLT-5) фільтрує звук, обчислює спектр і знаходить основні
частоти. Вони передають дані через `audio_contracts.AudioPacket`.
Початкові файли не змінюються.

## Встановлення

Потрібен Python 3.10 або новіший.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

У Windows замість `.venv/bin/python` використовуй `.venv\Scripts\python.exe`.

## MLT-4: швидкий запуск

Показати параметри одного або кількох файлів:

```bash
.venv/bin/python -m audio_io mono.wav broken.wav stereo.wav
```

Для кожного файла програма показує успіх і параметри або зрозумілу помилку.
Після помилки вона переходить до наступного файла. Наприкінці виводиться
кількість успішних і невдалих читань. Код завершення — `0`, якщо все прочитано,
і `1`, якщо хоча б один файл не прочитано; обробляються всі передані файли.

Демонстрація без підготовки власних WAV:

```bash
.venv/bin/python examples/wav_demo.py
```

Вона створює тимчасові моно, стерео, пошкоджений і порожній файли та показує,
що після помилки посередині списку правильний стереофайл також читається.
Очікуваний підсумок: 2 успішні файли й 2 повідомлення про помилки.
Це консольна демонстрація MLT-4; графічний інтерфейс і керування процесами
залишаються окремими модулями MLT-3 та MLT-2.

### API читання

```python
from audio_contracts import AudioReadError
from audio_io import WavSource, read_wav_batch, read_wav_details
from signal_proc import process_signal

sources = [
    WavSource("mono.wav", source_id="selection-1"),
    WavSource("broken.wav", source_id="selection-2"),
    WavSource("stereo.wav", source_id="selection-3"),
]
for result in read_wav_batch(sources):
    if isinstance(result, AudioReadError):
        print(result.source_id, result.message)
        continue
    processed = process_signal(result)
    print(processed.source_id, processed.peaks_by_channel)

# Коли також потрібна розрядність для показу користувачу:
details = read_wav_details("mono.wav", source_id="metadata-example")
if not isinstance(details, AudioReadError):
    print(details.bits_per_sample, details.encoding)
    print(details.packet.duration_seconds)
```

`read_wav(path, *, source_id, source_name=None)` повертає `AudioPacket` або
`AudioReadError`. `read_wav_details(...)` додатково повертає WAV-розрядність і
кодування в `WavFile`; готовий пакет міститься в `WavFile.packet`.
Спільний `AudioPacket` залишається без змін. `source_id` задає викликач;
у межах одного пакета ідентифікатори мають бути різними, навіть якщо назви
файлів однакові. Дубльований/порожній ID — помилка виклику API (`ValueError`).

`read_wav_batch` читає послідовно й видає результат кожного файла окремо,
без збереження всіх аудіомасивів усередині модуля. Порожній список означає,
що файлів не вибрано: результатів немає. Паралельне виконання — задача MLT-2.

### Підтримувані WAV та помилки

- RIFF/WAVE: PCM 8, 16, 24, 32 біти; IEEE float 32 та 64 біти.
- Моно, стерео й інші кількості каналів зберігаються окремо. Частота
  дискретизації має бути додатною; 8000 та 16000 Гц — приклади, не обмеження.
- Розрядність береться із заголовка файла. Наприклад, PCM24 зберігається
  SciPy в `int32` з вирівнюванням старших бітів; це все ще 24-бітний WAV.
  MLT-5 правильно нормалізує цей тип. Float зберігає свій масштаб.
- Вміст перевіряється незалежно від розширення та регістру імені.
  Допоміжні WAV-блоки з коректною довжиною дозволені.
- Перевіряються довжини RIFF і блоків, наявність `fmt`/`data`, узгодженість
  параметрів, повні кадри та кількість реально декодованих кадрів.
- RIFX, RF64/BW64, WAVE_FORMAT_EXTENSIBLE, стиснені WAV та інші розрядності
  в цій версії повертають `unsupported_format`.

| Код | Що означає |
| --- | --- |
| `empty_audio` | Файл 0 байтів або WAV без звукових кадрів |
| `invalid_wav` | Неправильний заголовок, обірвані/неузгоджені дані, NaN або Inf |
| `unsupported_format` | Розпізнаний, але непідтримуваний різновид WAV чи кодування |
| `read_failed` | Немає файла, немає доступу, шлях до папки або помилка читання |

Докладніше про перевірки й пояснення для захисту: [docs/MLT4.md](docs/MLT4.md).

## MLT-5: цифрова обробка сигналів

Модуль реалізує задачі MLT-23/9 (фільтрація), MLT-24/10 (FFT) та
MLT-25/11 (пошук домінуючих частот).

### Приклад

```python
import numpy as np
from audio_contracts import AudioPacket
from signal_proc import FilterConfig, process_signal

sample_rate = 8_000
time = np.arange(sample_rate) / sample_rate
samples = 0.8 * np.sin(2 * np.pi * 440 * time)
samples += 0.3 * np.sin(2 * np.pi * 1_000 * time)

input_packet = AudioPacket(
    source_id="generated-two-tone",
    source_name="generated-two-tone",
    sample_rate_hz=sample_rate,
    samples=samples,
)
packet = process_signal(
    input_packet,
    filter_config=FilterConfig(kind="lowpass", cutoff_hz=600),
)
print(packet.peaks_by_channel[0])
next_stage_payload = packet.to_payload()
```

Читання WAV та передавання його до MLT-5:

```python
from audio_contracts import AudioReadError
from audio_io import read_wav
from signal_proc import process_signal

input_packet = read_wav("example.wav", source_id="example-1")
if isinstance(input_packet, AudioReadError):
    print(input_packet.message)
else:
    packet = process_signal(input_packet)
    print(packet.peaks_by_channel)
```

## Контракт між читанням файлів і DSP

Кожен успішно декодований файл передається як один `audio_contracts.AudioPacket` версії 1. У пакеті є унікальний у межах запуску `source_id`, необов'язкове ім'я файла `source_name`, `sample_rate_hz` і `samples`. Моно зберігається як масив `(кадри, 1)`, багатоканальний сигнал — `(кадри, канали)`. Масив має бути числовим і C-contiguous; integer PCM передається у вихідному масштабі, float — у вихідному масштабі. `signal_proc` виконує нормалізацію integer PCM.

Читач файлів повертає `AudioReadResult`: для успіху — `AudioPacket`, для помилки окремого файла — малий `AudioReadError` із `source_id`, `error_code` і повідомленням. Оркестратор записує помилку й продовжує інші файли; `process_signal` приймає лише успішний `AudioPacket`.

Для процесів передавай сам dataclass через `multiprocessing.Queue`, а не JSON/base64 із великими масивами. Пакет — pickle-сумісний; після створення/передачі не змінюй `samples`. Черга серіалізує масив і може його копіювати. Якщо виміри покажуть, що це вузьке місце для великих WAV, наступним кроком може бути shared-memory дескриптор зі схемою тієї самої metadata; зараз цей рівень складності не потрібний.

Кожен функціональний модуль матиме власний пакет у `src/` (наприклад, `src/signal_proc/`). Спільні типи передачі даних належать `src/audio_contracts/`, щоб модулі не імпортували внутрішню реалізацію один одного.

## Контракт пакета

`process_signal(...)` повертає `SignalPacket` зі схемою версії `1`:

| Поле | Формат і значення |
| --- | --- |
| `source_id` | Ідентифікатор файлу або іншого джерела, переданий викликачем |
| `source_name` | Необов'язкова коротка назва джерела для відображення |
| `sample_rate_hz` | Ціла частота дискретизації |
| `samples` | `float64` NumPy-масив `(кількість кадрів, кількість каналів)` після фільтрації; без фільтра — копія вхідних даних |
| `spectrum.frequencies_hz` | Частоти бінів FFT, масив `(кількість бінів,)` |
| `spectrum.amplitudes` | Односторонні амплітуди, масив `(кількість бінів, кількість каналів)` |
| `spectrum.bin_width_hz`, `window`, `mean_removed`, `amplitude_scale` | Крок частот і правила обчислення спектра, потрібні для інтерпретації результату |
| `peaks_by_channel` | Кортеж списків піків для кожного каналу; у кожному списку піки відсортовані за спаданням амплітуди |
| `filter_config`, `peak_config` | Параметри, з якими отримано результат |
| `frame_count`, `channel_count`, `duration_seconds` | Похідні властивості пакета |

Пакет можна передавати через `multiprocessing.Queue`: його класи визначені
на рівні пакета Python і серіалізуються через `pickle`. Метод `to_payload()`
повертає словник з тими самими даними для інтеграції; великі числові масиви
залишаються NumPy-масивами. Для JSON їх треба зберегти окремо або явно
перетворити, щоб не створювати величезне повідомлення.

Моно-вхід `(кадри,)` приводиться до `(кадри, 1)`. Стерео та інші канали
аналізуються **окремо**, без змішування. Цілочисельний PCM перетворюється
на значення приблизно в межах `[-1, 1]`; `float` зберігає свій масштаб.
Фільтр Баттерворта причинний (`sosfilt`), тому на початку короткого сигналу
можливий перехідний процес. Для спектра віднімається середнє значення й
застосовується вікно Ганна. FFT і список піків описують саме вихідний,
у разі потреби відфільтрований, сигнал.

За замовчуванням повертаються до п'яти піків на канал з амплітудою
щонайменше 5% від найбільшого піка. DC-компонента (0 Гц) не включається.
Точність частоти обмежена кроком FFT `sample_rate_hz / frame_count`;
для сигналів із частотами між бінами результат треба порівнювати з допуском.
Амплітуда такого сигналу також може бути меншою за амплітуду відповідної
синусоїди через розподіл енергії між сусідніми бінами.

## Покриття задач MLT-5

| Вимога | Реалізація |
| --- | --- |
| MLT-23/9: обрати та застосувати фільтр | `FilterConfig`, фільтри низьких і високих частот |
| MLT-23: зберегти оригінал | Вхід копіюється; модуль не записує файли |
| MLT-24/10: FFT, частоти й амплітуди | `SignalSpectrum` у вихідному пакеті |
| MLT-25/11: домінуючі частоти | `peaks_by_channel`, сортування за амплітудою |

Читання пошкодженого WAV перевіряється на етапі MLT-4, а графічне
відображення пакета належить етапу MLT-3. Цей модуль передає їм дані через
описаний вище контракт.

