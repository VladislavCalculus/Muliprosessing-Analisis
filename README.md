# MLT-5: цифрова обробка сигналів

Модуль реалізує задачі MLT-23/9 (фільтрація), MLT-24/10 (FFT) та
MLT-25/11 (пошук домінуючих частот). Він приймає вже декодовані аудіодані:
читання WAV належить модулю MLT-4. Файлів модуль не змінює.

## Встановлення

Потрібен Python 3.10 або новіший.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

## Приклад

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

Якщо WAV уже читається через SciPy, інтеграція з етапом MLT-4 виглядає так:

```python
from pathlib import Path
from scipy.io import wavfile
from audio_contracts import AudioPacket
from signal_proc import process_signal

path = Path("example.wav")
sample_rate, samples = wavfile.read(path)
input_packet = AudioPacket(
    source_id=str(path.resolve()),
    source_name=path.name,
    sample_rate_hz=sample_rate,
    samples=samples,
)
packet = process_signal(input_packet)
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

