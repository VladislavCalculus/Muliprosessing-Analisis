"""Build the individual MLT-5 testing protocol as a DOCX document."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "Протокол_тестування_MLT-5_Лакей.docx"


CASES = [
    {
        "id": "TC-MLT5-01",
        "title": "FFT і пік для однієї синусоїди",
        "kind": "Позитивний",
        "tasks": "MLT-24, MLT-10, MLT-25, MLT-11",
        "data": "fs = 8000 Гц; N = 8000; x = tone(440, 0.8). Фільтр не застосовується.",
        "steps": "1. Згенерувати x за спільною формулою.\n2. Викликати process_signal(x, fs, source_id='TC-01').\n3. Прочитати spectrum і peaks_by_channel[0].",
        "expected": "Пакет має 8000 кадрів, 1 канал і тривалість 1 с. Крок частот становить 1 Гц. Найбільший пік — 440 Гц; його амплітуда та амплітуда відповідного біна FFT — 0.8 ± 0.02.",
        "pass": "Усі поля пакета відповідають наведеним значенням; виклик завершується без винятку.",
    },
    {
        "id": "TC-MLT5-02",
        "title": "Дві частоти та порядок домінуючих піків",
        "kind": "Позитивний",
        "tasks": "MLT-24, MLT-10, MLT-25, MLT-11",
        "data": "fs = 8000 Гц; N = 8000; x = tone(440, 0.8) + tone(1000, 0.3).",
        "steps": "1. Згенерувати суму двох синусоїд.\n2. Викликати process_signal(x, fs, source_id='TC-02').\n3. Переглянути перші два елементи peaks_by_channel[0].",
        "expected": "Перший пік — 440 Гц з амплітудою 0.8 ± 0.02; другий — 1000 Гц з амплітудою 0.3 ± 0.02. Піки впорядковані за спаданням амплітуди.",
        "pass": "Обидві частоти знайдені в указаному порядку, а амплітуди лежать у заданих інтервалах.",
    },
    {
        "id": "TC-MLT5-03",
        "title": "Фільтр низьких частот і незмінність входу",
        "kind": "Позитивний",
        "tasks": "MLT-23, MLT-9, MLT-24, MLT-10",
        "data": "fs = 8000 Гц; N = 8000; x = tone(440, 0.8) + tone(1000, 0.3); filter_config = FilterConfig('lowpass', cutoff_hz=600, order=4).",
        "steps": "1. Зберегти копію x до обробки.\n2. Викликати process_signal(x, fs, source_id='TC-03', filter_config=filter_config).\n3. Порівняти x з копією; визначити амплітуди спектра на 440 і 1000 Гц.",
        "expected": "Амплітуда 440 Гц > 0.65; амплітуда 1000 Гц < 0.05. Найбільший пік — 440 Гц. Вхідний масив x не змінився; у пакеті зазначено тип фільтра lowpass.",
        "pass": "Обидві спектральні межі виконані, x і його копія побітово рівні, а параметри фільтра збережені в пакеті.",
    },
    {
        "id": "TC-MLT5-04",
        "title": "Альтернативний тип фільтра: високі частоти",
        "kind": "Альтернативний",
        "tasks": "MLT-23, MLT-9, MLT-25, MLT-11",
        "data": "fs = 8000 Гц; N = 8000; x = tone(440, 0.8) + tone(1000, 0.3); filter_config = FilterConfig('highpass', cutoff_hz=700, order=4).",
        "steps": "1. Згенерувати x.\n2. Викликати process_signal(x, fs, source_id='TC-04', filter_config=filter_config).\n3. Визначити амплітуди на 440 і 1000 Гц та перший пік.",
        "expected": "Амплітуда 440 Гц < 0.20; амплітуда 1000 Гц > 0.25. Перший домінуючий пік — 1000 Гц; у пакеті зазначено highpass.",
        "pass": "Виконані обидві спектральні межі, порядок піків і значення типу фільтра.",
    },
    {
        "id": "TC-MLT5-05",
        "title": "Окрема обробка лівого й правого каналів",
        "kind": "Альтернативний",
        "tasks": "MLT-24, MLT-10, MLT-25, MLT-11",
        "data": "fs = 8000 Гц; N = 8000; x = np.column_stack((tone(440, 0.8), tone(1000, 0.3))).",
        "steps": "1. Створити двоканальний масив x.\n2. Викликати process_signal(x, fs, source_id='TC-05').\n3. Перевірити форму масивів і перший пік кожного каналу.",
        "expected": "samples має форму (8000, 2), spectrum.amplitudes — (4001, 2). У каналі 0 найбільший пік 440 Гц, у каналі 1 — 1000 Гц; канали не змішані.",
        "pass": "Кількість каналів, форми масивів і частоти піків точно відповідають очікуваним.",
    },
    {
        "id": "TC-MLT5-06",
        "title": "Альтернативний формат вхідних відліків: 8-бітний PCM",
        "kind": "Альтернативний",
        "tasks": "MLT-24, MLT-10, MLT-25, MLT-11",
        "data": "fs = 8000 Гц; N = 8000; x = np.clip(np.rint(128 + 64 * tone(440)), 0, 255).astype(np.uint8).",
        "steps": "1. Створити масив x типу uint8 за формулою.\n2. Викликати process_signal(x, fs, source_id='TC-06').\n3. Перевірити тип вихідних samples і найбільший пік.",
        "expected": "Вихідні samples мають тип float64 і форму (8000, 1). Найбільший пік — 440 Гц з амплітудою 0.50 ± 0.03. Вхідний x зберігає тип uint8 і свої значення.",
        "pass": "Типи, форма, частота, діапазон амплітуди та незмінність входу відповідають очікуваним.",
    },
    {
        "id": "TC-MLT5-07",
        "title": "Тиша як граничний сигнал",
        "kind": "Граничний",
        "tasks": "MLT-24, MLT-10, MLT-25, MLT-11",
        "data": "fs = 8000 Гц; x = np.zeros(256), тобто 256 нульових відліків.",
        "steps": "1. Створити масив тиші.\n2. Викликати process_signal(x, fs, source_id='TC-07').\n3. Переглянути спектр і peaks_by_channel[0].",
        "expected": "Пакет містить 256 кадрів; усі амплітуди спектра дорівнюють нулю; список піків порожній. Помилки або поділу на нуль немає.",
        "pass": "Усі три умови виконані, виклик завершується без винятку.",
    },
    {
        "id": "TC-MLT5-08",
        "title": "Частота між сусідніми бінами FFT",
        "kind": "Граничний",
        "tasks": "MLT-24, MLT-10, MLT-25, MLT-11",
        "data": "fs = 8000 Гц; N = 8000; x = tone(1234.5, 1.0).",
        "steps": "1. Згенерувати синусоїду з частотою 1234.5 Гц.\n2. Викликати process_signal(x, fs, source_id='TC-08').\n3. Прочитати spectrum.bin_width_hz і частоту найбільшого піка.",
        "expected": "Крок FFT становить 1 Гц. Найбільший пік лежить на 1234 або 1235 Гц; абсолютна похибка щодо 1234.5 Гц не перевищує 0.5 Гц. Амплітуда піка може відрізнятися від 1 через розподіл енергії між бінами.",
        "pass": "Частотний крок і допуск похибки виконані; некоректний точний критерій для амплітуди не застосовується.",
    },
    {
        "id": "TC-MLT5-09",
        "title": "Передача вихідного пакета наступному етапу",
        "kind": "Позитивний",
        "tasks": "MLT-24, MLT-25; контракт результату модуля",
        "data": "fs = 8000 Гц; N = 8000; x = tone(440, 0.8).",
        "steps": "1. Отримати packet = process_signal(x, fs, source_id='TC-09').\n2. Отримати payload = packet.to_payload().\n3. Виконати restored = pickle.loads(pickle.dumps(packet)).\n4. Порівняти поля та масиви packet і restored.",
        "expected": "payload містить schema_version=1, source_id, sample_rate_hz, samples, spectrum і peaks_by_channel. Поля spectrum описують крок 1 Гц та вікно periodic_hann. Після серіалізації source_id, форма масивів, значення відліків і частота піка збережені.",
        "pass": "Усі обов'язкові поля присутні, а відновлений пакет чисельно збігається з початковим.",
    },
    {
        "id": "TC-MLT5-10",
        "title": "Недопустима частота зрізу на межі Найквіста",
        "kind": "Негативний, граничний",
        "tasks": "MLT-23, MLT-9",
        "data": "fs = 8000 Гц; x = tone(440, 0.8); FilterConfig('lowpass', cutoff_hz=4000).",
        "steps": "1. Зберегти копію x.\n2. Викликати process_signal(x, fs, source_id='TC-10', filter_config=FilterConfig('lowpass', 4000)).\n3. Перевірити тип помилки та незмінність x.",
        "expected": "Оскільки 4000 Гц дорівнює частоті Найквіста, виклик породжує ValueError з поясненням про межу Найквіста. Вхідний масив x не змінюється.",
        "pass": "Отримано саме ValueError до формування пакета; x дорівнює збереженій копії.",
    },
    {
        "id": "TC-MLT5-11",
        "title": "Необчислюване значення у вхідному сигналі",
        "kind": "Негативний",
        "tasks": "MLT-24, MLT-10",
        "data": "fs = 8000 Гц; x = np.array([0.0, np.nan]).",
        "steps": "1. Створити масив із NaN.\n2. Викликати process_signal(x, fs, source_id='TC-11').\n3. Зафіксувати тип винятку.",
        "expected": "Виклик породжує ValueError із повідомленням про допустимість лише скінченних значень. Пакет з некоректним спектром не повертається.",
        "pass": "Отримано ValueError; результат обробки не сформовано.",
    },
    {
        "id": "TC-MLT5-12",
        "title": "Порожній вхідний масив",
        "kind": "Негативний, граничний",
        "tasks": "MLT-24, MLT-10, MLT-25, MLT-11",
        "data": "fs = 8000 Гц; x = np.array([]).",
        "steps": "1. Створити порожній масив.\n2. Викликати process_signal(x, fs, source_id='TC-12').\n3. Зафіксувати тип винятку.",
        "expected": "Виклик породжує ValueError з поясненням, що потрібні аудіокадри. FFT не запускається, пакет не повертається.",
        "pass": "Отримано ValueError; аварійного завершення інтерпретатора немає.",
    },
]


CHECKS = [
    ("CL-01", "Монотон 440 Гц: FFT повертає шкалу частот із кроком 1 Гц.", "Крок дорівнює 1 Гц."),
    ("CL-02", "Монотон 440 Гц: амплітуда та пік відповідають відомому сигналу.", "440 Гц; 0.8 ± 0.02."),
    ("CL-03", "Сума тонів 440 і 1000 Гц: піки впорядковані за амплітудою.", "Перший 440 Гц, другий 1000 Гц."),
    ("CL-04", "Фільтр lowpass 600 Гц послаблює компоненту 1000 Гц.", "Амплітуда 1000 Гц < 0.05."),
    ("CL-05", "Фільтр highpass 700 Гц послаблює компоненту 440 Гц.", "Амплітуда 440 Гц < 0.20."),
    ("CL-06", "Фільтрація не змінює вхідний масив.", "Вхід дорівнює копії до виклику."),
    ("CL-07", "Стереоканали аналізуються незалежно.", "440 Гц у каналі 0; 1000 Гц у каналі 1."),
    ("CL-08", "Вхід uint8 PCM масштабується до float64.", "Тип float64; пік 440 Гц, амплітуда 0.50 ± 0.03."),
    ("CL-09", "Тиша не створює хибних домінуючих частот.", "Амплітуди нульові; список піків порожній."),
    ("CL-10", "Частота між бінами FFT повертається з обумовленою похибкою.", "Для 1234.5 Гц похибка піка ≤ 0.5 Гц."),
    ("CL-11", "Вихідний пакет має потрібні поля та версію схеми.", "schema_version=1; масиви, частоти, піки, source_id присутні."),
    ("CL-12", "Пакет проходить серіалізацію для передачі між процесами.", "Після pickle відліки, форма та піки не змінені."),
    ("CL-13", "Частота зрізу, рівна або більша за fs/2, відхиляється.", "ValueError; пакет не повертається."),
    ("CL-14", "Невідомий тип фільтра відхиляється.", "ValueError під час створення FilterConfig."),
    ("CL-15", "NaN або нескінченність у вхідних даних відхиляється.", "ValueError; некоректний спектр не повертається."),
    ("CL-16", "Порожній масив відхиляється.", "ValueError; FFT не запускається."),
    ("CL-17", "Нульова чи від'ємна частота дискретизації відхиляється.", "ValueError."),
    ("CL-18", "Порожній source_id відхиляється.", "ValueError."),
]


def shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_text(cell, value: str, *, bold: bool = False) -> None:
    cell.text = ""
    for index, line in enumerate(value.split("\n")):
        paragraph = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(line)
        run.bold = bold
        run.font.size = Pt(10)


def add_case(document: Document, case: dict[str, str]) -> None:
    document.add_heading(f"{case['id']}. {case['title']}", level=2)
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.columns[0].width = Cm(3.3)
    table.columns[1].width = Cm(13.0)
    for label, value in [
        ("Тип сценарію", case["kind"]),
        ("Задачі Jira", case["tasks"]),
        ("Передумови / дані", case["data"]),
        ("Кроки", case["steps"]),
        ("Очікуваний результат", case["expected"]),
        ("Критерій успіху", case["pass"]),
        ("Фактичний результат", "____________________  Статус: ☐ Pass  ☐ Fail  ☐ Not run"),
    ]:
        left, right = table.add_row().cells
        left.vertical_alignment = right.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        shade(left, "EAF0F7")
        set_cell_text(left, label, bold=True)
        set_cell_text(right, value)
    document.add_paragraph().paragraph_format.space_after = Pt(2)


def add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    paragraph.add_run("Стор. ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    paragraph._p.append(field)


def build() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.3)
    section.right_margin = Cm(1.8)
    section.header_distance = Cm(1)
    section.footer_distance = Cm(1)

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    for name, size in [("Title", 17), ("Heading 1", 14), ("Heading 2", 12)]:
        style = doc.styles[name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(25, 49, 83)
        style.paragraph_format.keep_with_next = True
    add_page_number(section.footer.paragraphs[0])

    for line in [
        "НАЦІОНАЛЬНИЙ ТЕХНІЧНИЙ УНІВЕРСИТЕТ УКРАЇНИ",
        "«КИЇВСЬКИЙ ПОЛІТЕХНІЧНИЙ ІНСТИТУТ ІМЕНІ ІГОРЯ СІКОРСЬКОГО»",
        "Навчально-науковий інститут атомної та теплової енергетики",
        "Кафедра інженерії програмного забезпечення в енергетиці",
    ]:
        p = doc.add_paragraph(line)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("\n\n")
    title = doc.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("ПРОТОКОЛ\nрозроблення тест-кейсів і чек-листа")
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.add_run("Функціональний модуль MLT-5 «Цифрова обробка сигналів»\n")
    subtitle.add_run("Проєкт «Багатопроцесна система обробки сигналів»")
    doc.add_paragraph("\n\n")
    author = doc.add_paragraph()
    author.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    author.add_run("Виконав: студент групи ТВ-42\nЛакей Владислав Михайлович\n")
    author.add_run("Перевірив: Варава Іван Андрійович")
    doc.add_paragraph("Дата складання: 15.10.2026")
    doc.add_paragraph("\n\n")
    city = doc.add_paragraph("Київ — 2026")
    city.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()

    doc.add_heading("1. Опис функціонального модуля", level=1)
    doc.add_paragraph(
        "MLT-5 — самостійний етап цифрової обробки аудіосигналу. На вхід подаються "
        "декодовані відліки одного або кількох каналів, частота дискретизації та "
        "необов'язкові параметри фільтра й пошуку піків. Модуль можна тестувати "
        "без WAV-парсера, графічного інтерфейсу та багатопроцесної частини."
    )
    doc.add_paragraph(
        "Функції: (1) фільтрація низьких або високих частот; (2) FFT із частотною "
        "шкалою й амплітудами; (3) виділення та сортування домінуючих частот окремо "
        "для кожного каналу. Модуль охоплює User Stories MLT-23, MLT-24, MLT-25 "
        "та технічні задачі MLT-9, MLT-10, MLT-11."
    )
    doc.add_paragraph(
        "Вихід — SignalPacket зі схемою версії 1. Він містить source_id, "
        "sample_rate_hz, відфільтровані samples, спектр, списки піків за каналами "
        "та параметри обробки. Метод to_payload() надає словник для наступного етапу. "
        "Початковий масив і вихідний WAV-файл не змінюються."
    )
    doc.add_paragraph(
        "Межі тестування: читання або перевірка пошкоджених WAV належить MLT-4; "
        "відображення графіків — MLT-3; розподіл між процесами — MLT-2. Ці функції "
        "не потрібні для незалежної перевірки MLT-5."
    )

    doc.add_heading("2. Спільні передумови та тестові дані", level=1)
    doc.add_paragraph(
        "Середовище: Python 3.10 або новіший, NumPy >=2.1,<3, SciPy >=1.15,<2. "
        "Пакет встановлюється з кореня проєкту командою «python -m pip install -e .». "
        "Виклики виконуються в Python з import numpy as np та "
        "from mlt_signal import FilterConfig, process_signal. Для TC-09 також потрібен import pickle."
    )
    doc.add_paragraph(
        "Основний набір: fs = 8000 Гц, N = 8000 відліків, "
        "t = np.arange(N) / fs. Позначення tone(f, a) означає "
        "a × sin(2π × f × t). Кожен кейс створює новий масив x; "
        "жоден не залежить від результату попереднього."
    )
    code = doc.add_paragraph()
    code.paragraph_format.left_indent = Cm(0.7)
    run = code.add_run(
        "fs = 8000\nN = 8000\nt = np.arange(N) / fs\n"
        "def tone(f, a=1.0):\n    return a * np.sin(2 * np.pi * f * t)\n"
        "def amplitude_at(packet, f, channel=0):\n"
        "    i = np.argmin(np.abs(packet.spectrum.frequencies_hz - f))\n"
        "    return float(packet.spectrum.amplitudes[i, channel])"
    )
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    doc.add_paragraph(
        "Частоту піка порівнюють у герцах. Для амплітуд застосовано допуски, "
        "наведені в кейсах. Виняток є успішним результатом лише в негативних кейсах, "
        "де його тип зазначено явно. Поле «Фактичний результат» заповнюється під час виконання."
    )

    doc.add_heading("3. Тест-кейси", level=1)
    doc.add_paragraph(
        f"Розроблено {len(CASES)} незалежних кейсів: позитивні, альтернативні, "
        "граничні й негативні сценарії. Кожен містить дані, кроки, очікуваний "
        "результат і критерій успіху."
    )
    for case in CASES:
        add_case(doc, case)

    doc.add_heading("4. Чек-лист модуля MLT-5", level=1)
    doc.add_paragraph(
        f"Чек-лист містить {len(CHECKS)} перевірок. Позначку Pass/Fail/Not run "
        "та короткий фактичний результат проставляють після виконання."
    )
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, header in zip(table.rows[0].cells, ["ID", "Що перевірити", "Очікуваний результат", "Статус"]):
        shade(cell, "D9E5F2")
        set_cell_text(cell, header, bold=True)
    for check_id, description, expected in CHECKS:
        cells = table.add_row().cells
        for cell, value in zip(cells, [check_id, description, expected, "☐ P ☐ F ☐ N"]):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_text(cell, value)
    doc.add_paragraph(
        "Позначення: P — Pass, F — Fail, N — Not run. Цей документ фіксує "
        "розроблені перевірки; результати їх фактичного виконання в ньому не заявлені."
    )

    doc.add_heading("5. Висновок", level=1)
    doc.add_paragraph(
        "Для індивідуального модуля MLT-5 підготовлено 12 відтворюваних тест-кейсів "
        "і чек-лист із 18 перевірок. Набір охоплює фільтрацію, FFT, домінуючі "
        "частоти, багатоканальний сигнал, формати відліків, контракт вихідного "
        "пакета та обробку некоректного входу. Очікувані числові результати "
        "визначено для детермінованих синтетичних сигналів."
    )
    doc.save(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    print(build())
