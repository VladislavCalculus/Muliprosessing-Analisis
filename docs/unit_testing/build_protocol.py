"""Build DOCX/PDF/TXT from the saved pytest and Coverage.py evidence."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import textwrap
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def report_blocks():
    env = json.loads((HERE / "environment.json").read_text())
    for name, digest in env["sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Evidence is stale: rerun coverage for {name}")
    source = (ROOT / env["test_file"]).read_text()
    tests = [node for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
    output = (HERE / "pytest.txt").read_text()
    passed = re.search(r"(\d+) passed in ([\d.]+)s", output)
    if not passed or int(passed[1]) != len(tests):
        raise ValueError("Saved pytest output does not match the test source")
    data = json.loads((HERE / "coverage.json").read_text())
    totals = data["totals"]
    statements = 100 * totals["covered_lines"] / totals["num_statements"]
    branches = 100 * totals["covered_branches"] / totals["num_branches"]
    blocks = []

    def add(kind, value):
        blocks.append((kind, value))

    add("title", "ЗВІТ З ПРАКТИЧНОЇ РОБОТИ")
    add("p", "Тема: модульне тестування та оцінка покриття програмного модуля.")
    add("h", "1. Мета та об’єкт тестування")
    add("p", "Перевірити модуль цифрової обробки сигналів signal_proc (MLT-5) мовою Python: "
        "нормалізацію PCM, фільтрацію, FFT, пошук піків і формування результату. "
        "Використано pytest, unittest.mock і Coverage.py. Вхід — AudioPacket із синтетичним "
        "NumPy-масивом; читання WAV і графічний інтерфейс не входять у цей обсяг.")
    versions = ", ".join(f"{name} {version}" for name, version in env["versions"].items())
    add("p", f"Вимірювання: {env['date']}, macOS, Python {env['python']}; {versions}. "
        "Використано наявний компактний набір: 10 тестових функцій без збільшення їх кількості. "
        "Параметри сигналів відомі за побудовою; обладнання й аудіофайли не потрібні.")
    add("h", "2. Тестові сценарії")
    scenarios = [
        ("FFT і порядок піків", "440 Гц; суміш 200/600 Гц; крок FFT 1 Гц, очікувані амплітуди"),
        ("Незалежність каналів", "Стерео: різні тони й амплітуди, окремі списки піків"),
        ("Реальні фільтри", "Low-pass 600 Гц та high-pass 700 Гц послаблюють задані складові; вхід незмінний"),
        ("Stub і mock", "Параметри butter, один виклик sosfilt, передача SOS та фільтрованих кадрів"),
        ("Масштаб PCM", "int16 та uint8 → float64; амплітуда близько 0,5; вхід незмінний"),
        ("Непарна довжина FFT", "801 кадр: правильна форма спектра й амплітуда 0,4"),
        ("Граничні сигнали", "Пік Найквіста; один кадр і тиша дають нульовий спектр та порожні піки"),
        ("Правила пошуку піків", "Мінімальна частота, поріг, відстань і max_peaks"),
        ("Некоректні аргументи", "ValueError/TypeError для конфігурацій, типів, NaN, порожнього входу та cutoff Найквіста"),
        ("Вихідний пакет", "Поля payload, schema v1, відсутній фільтр і збереження масивів/піків після pickle"),
    ]
    add("table", [["№", "Перевірка", "Очікуваний результат"]] +
        [[str(i), name, expected] for i, (name, expected) in enumerate(scenarios, 1)])
    add("h", "3. Типи перевірок assert")
    add("table", [
        ["Засіб", "Застосування в лістингу"],
        ["assert a == b; is; is None", "Форма, dtype, конфігурація, schema v1, ідентичність SOS та відсутність фільтра"],
        ["assert a > b / a < b", "Проходження корисної частоти й послаблення частоти поза смугою"],
        ["pytest.approx", "Частоти й амплітуди з допуском для обчислень із рухомою комою"],
        ["np.testing.assert_array_equal", "Точна рівність масивів і незмінність початкових даних"],
        ["pytest.raises(..., match=...)", "Тип винятку та фрагмент його повідомлення"],
        ["Mock.assert_called_once()", "Рівно один виклик залежності sosfilt"],
    ])
    add("h", "4. Два тестові двійники")
    add("p", "У test_filter_backend_uses_stub_and_mock функція butter_stub замінює "
        "scipy.signal.butter і повертає заздалегідь заданий sos_marker. Це stub — "
        "заглушка, яка задає контрольовану відповідь залежності; список butter_calls "
        "додатково реєструє аргументи. Другий двійник — unittest.mock.Mock замість "
        "scipy.signal.sosfilt: повертає нульові кадри та дозволяє перевірити кількість "
        "викликів, SOS-маркер, вхідні дані й axis=0. monkeypatch відновлює залежності "
        "після тесту. Окремий сценарій із реальними low/high-pass фільтрами перевіряє "
        "їхню числову дію без підмін.")
    add("h", "5. Запуск та фактичні результати")
    add("p", "Із кореня репозиторію після активації .venv:")
    add("code", "python -m pip install -e '.[test]'\n" + "\n".join(env["commands"]))
    add("p", f"Фактичний результат: {passed[1]} passed in {passed[2]}s. "
        "Повний вивід збережено в docs/unit_testing/pytest.txt; детальний звіт — "
        "coverage.txt і coverage.json. Coverage.py вимірював лише signal_proc; "
        "бібліотеки SciPy/NumPy, тести й пакет audio_contracts не входять у знаменник.")
    add("code", (HERE / "coverage.txt").read_text().strip())
    add("p", f"Виконано {totals['covered_lines']} із {totals['num_statements']} операторів "
        f"({statements:.2f}%) і {totals['covered_branches']} із {totals['num_branches']} "
        f"переходів гілок ({branches:.2f}%). Сумарний показник Coverage.py — "
        f"{totals['percent_covered']:.2f}% (у консольному звіті округлено до 97%). "
        "Він враховує оператори та переходи, тому відрізняється від покриття операторів.")
    add("p", "Не виконані рядки processing.py 194–195 (резервне вікно при нульовій сумі) "
        "та 218–219 (мінімальна частота вище всіх бінів); частково покритий перехід "
        "243→245 — відхилення кандидата через мінімальну відстань між піками. "
        "Набір не розширювався заради 100%; покриття не доводить коректність усіх "
        "можливих сигналів. У цьому прогоні падінь тестів не виявлено.")
    add("h", "6. Підсумок")
    add("p", "Набір із 10 тестів перевіряє основні, граничні й негативні сценарії "
        "обраного модуля. Продемонстровано кілька видів assert і два тестові двійники: "
        "stub та mock. Оцінено покриття операторів і гілок; повний лістинг наведено нижче.")
    add("h", "7. Повний лістинг модульних тестів")
    add("p", "Файл test/test_signal_proc.py. Нумерація сценаріїв у розділі 2 відповідає "
        "порядку test_* функцій у цьому лістингу. Довгі рядки перенесено для верстки; "
        "виконуваний оригінал міститься у зазначеному файлі репозиторію.")
    add("code", source.rstrip())
    return blocks


def code_lines(text):
    return "\n".join(
        part for line in text.splitlines()
        for part in (textwrap.wrap(line, width=86, subsequent_indent="    ",
                                  replace_whitespace=False, drop_whitespace=False) or [""])
    )


def build_docx(blocks):
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2.54)
    section.left_margin = section.right_margin = Cm(2.54)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Arial", Pt(11)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(0)
    for name, size in [("Title", 20), ("Heading 1", 16)]:
        style = doc.styles[name]
        style.font.name, style.font.size = "Arial", Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.bold = False
    for kind, value in blocks:
        if kind == "page":
            doc.add_page_break()
        elif kind == "table":
            table = doc.add_table(rows=0, cols=len(value[0]))
            table.style = "Table Grid"
            table.autofit = False
            ratios = [.07, .29, .64] if len(value[0]) == 3 else [.43, .57]
            for col, ratio in zip(table.columns, ratios):
                col.width = Cm(15.92 * ratio)
            for i, row in enumerate(value):
                cells = table.add_row().cells
                props = table.rows[-1]._tr.get_or_add_trPr()
                props.append(OxmlElement("w:cantSplit"))
                if i == 0:
                    props.append(OxmlElement("w:tblHeader"))
                for cell, text, ratio in zip(cells, row, ratios):
                    cell.width = Cm(15.92 * ratio)
                    cell.text = text
                    if i == 0:
                        shade = OxmlElement("w:shd")
                        shade.set(qn("w:fill"), "CFE2F3")
                        cell._tc.get_or_add_tcPr().append(shade)
                    for p in cell.paragraphs:
                        p.paragraph_format.line_spacing = 1
                        for run in p.runs:
                            run.bold = i == 0
            doc.add_paragraph()
        elif kind == "code":
            for line in code_lines(value).split("\n"):
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing = 1
                p.paragraph_format.space_after = Pt(0)
                run = p.add_run(line)
                run.font.name, run.font.size = "Courier New", Pt(8.5 if line else 4)
        else:
            doc.add_paragraph(value, {"title": "Title", "h": "Heading 1"}.get(kind))
    doc.core_properties.title = "Модульне тестування signal_proc (MLT-5)"
    doc.core_properties.author = ""
    doc.save(HERE / "protocol.docx")


def build_pdf(blocks, font_dir):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    for name, filename in [("Arial", "Arial.ttf"), ("ArialBold", "Arial Bold.ttf"),
                           ("Mono", "Courier New.ttf")]:
        pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    styles = {
        "p": ParagraphStyle("p", fontName="Arial", fontSize=11, leading=12.65),
        "title": ParagraphStyle("title", fontName="Arial", fontSize=20, leading=23,
                                spaceAfter=12, keepWithNext=True),
        "h": ParagraphStyle("h", fontName="Arial", fontSize=16, leading=18.4,
                            spaceBefore=18, spaceAfter=6, keepWithNext=True),
        "code": ParagraphStyle("code", fontName="Mono", fontSize=8.5, leading=10.2),
        "cell": ParagraphStyle("cell", fontName="Arial", fontSize=11, leading=12),
        "header": ParagraphStyle("header", fontName="ArialBold", fontSize=11, leading=12),
    }
    width = A4[0] - 5.08 * cm
    story = []
    for kind, value in blocks:
        if kind == "page":
            story.append(PageBreak())
        elif kind == "code":
            chunk = []
            for line in code_lines(value).split("\n") + [""]:
                if line:
                    chunk.append(line)
                else:
                    if chunk:
                        story.append(Preformatted("\n".join(chunk), styles["code"]))
                        chunk = []
                    story.append(Spacer(1, 4))
        elif kind == "table":
            rows = [[Paragraph(escape(cell), styles["header" if i == 0 else "cell"])
                     for cell in row] for i, row in enumerate(value)]
            ratios = [.07, .29, .64] if len(value[0]) == 3 else [.43, .57]
            table = Table(rows, colWidths=[width * r for r in ratios], repeatRows=1)
            table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#CFE2F3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.extend([table, Spacer(1, 6)])
        else:
            story.append(Paragraph(escape(value), styles[kind]))
    SimpleDocTemplate(str(HERE / "protocol.pdf"), pagesize=A4,
                      leftMargin=2.54*cm, rightMargin=2.54*cm,
                      topMargin=2.54*cm, bottomMargin=2.54*cm,
                      title="Модульне тестування signal_proc (MLT-5)", author="").build(story)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path,
                        default=Path("/System/Library/Fonts/Supplemental"))
    args = parser.parse_args()
    blocks = report_blocks()
    (HERE / "protocol.txt").write_text("\n\n".join(
        "\n".join(" | ".join(row) for row in value) if kind == "table" else value
        for kind, value in blocks if kind != "page"
    ) + "\n")
    build_docx(blocks)
    build_pdf(blocks, args.font_dir)
    print("Built protocol.txt, protocol.docx, protocol.pdf")
