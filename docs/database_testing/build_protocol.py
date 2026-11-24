"""Render the database coursework protocol from actual saved test evidence."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TITLE = "Тестування реляційної бази даних результатів аудіоаналізу"


def report_blocks():
    env = json.loads((HERE / "environment.json").read_text())
    for name, digest in env["sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Saved evidence is stale for {name}")
    test_source = (ROOT / env["test_file"]).read_text()
    tests = [node for node in ast.parse(test_source).body
             if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
    output = (HERE / "pytest.txt").read_text()
    summary = re.search(r"(\d+) passed in ([\d.]+)s", output)
    if not summary or int(summary[1]) != len(tests):
        raise ValueError("Test count differs from saved pytest evidence")
    blocks = []

    def add(kind, value):
        blocks.append((kind, value))

    add("title", "ЗВІТ З ПРАКТИЧНОЇ РОБОТИ")
    add("p", "Тема: " + TITLE + ".")
    add("h", "1. Мета та об’єкт тестування")
    add("p", "Провести тестування реляційної бази даних інформаційної системи "
        "пакетного аналізу WAV-аудіо. Перевірити таблиці, поля, зв’язки, обмеження, "
        "тригери, SQL-обчислення та транзакції відповідно до правил збереження "
        "результатів. Використано Python, pytest і реальну SQLite; "
        "підміна СУБД тестовими двійниками не застосовується.")
    add("p", f"Середовище: {env['date']}, Python {env['python']}, "
        f"SQLite {env['sqlite']}, pytest {env['pytest']}. "
        "Робота є продовженням модульного тестування MLT-5: наявний DSP формує "
        "результати, MLT-2 збирає їх, а окремий result_store зберігає історію. "
        "Майбутній вебінтерфейс MLT-3 використовуватиме це сховище через backend.")
    add("h", "2. Структура БД і бізнес-правила")
    add("p", "Ланцюжок master–detail: analysis_run (запуск) 1:N file_result "
        "(результат обробки файла) 1:N spectral_peak (спектральний пік). "
        "Це два послідовні зв’язки через зовнішні ключі. Повторний аналіз того "
        "самого WAV належить іншому запуску й може мати інші параметри.")
    add("table", [
        ["Таблиця", "Призначення"],
        ["analysis_run", "Параметри та стан одного запуску аналізу"],
        ["file_result", "Ідентифікація джерела, метадані, успішний результат або помилка"],
        ["spectral_peak", "Канал, частота в Гц та амплітуда знайденого піка"],
    ])
    add("p", "Точні правила типів, допустимих значень, унікальності й видалення "
        "визначені SQL-скриптом у розділі 4. Для помилки читання метадані не "
        "вигадуються; відсутність піків також можлива для успішного аналізу тиші. "
        "Один результат і його піки мають записуватися атомарно. З’єднання "
        "використовує ввімкнений контроль зовнішніх ключів.")
    add("p", "SQLite не підтримує звичайні SQL-збережені процедури CREATE PROCEDURE/CALL. "
        "Тому такі процедури не заявляються створеними або протестованими. "
        "Перевіряються наявні SQL-компоненти обраної СУБД; Python API сховища "
        "не називається збереженою процедурою.")
    add("h", "3. Сценарії та фактичний результат")
    add("table", [["Тестова функція", "Перевірка"]] + [
        [node.name, ast.get_docstring(node) or node.name.removeprefix("test_").replace("_", " ")]
        for node in tests
    ])
    add("p", "Кожен сценарій створює власну тестову базу/ізольовані дані. "
        "У перевірках зіставляються реальні SQL-результати, очікувані помилки "
        "обмежень і стан БД після операцій; виробнича база не використовується.")
    add("code", "\n".join(env["commands"]))
    add("p", f"Фактично отримано: {summary[1]} passed in {summary[2]}s. "
        "Повний вивід збережено поруч у pytest.txt. Повний SQL і тестовий код "
        "нижче відповідають перевіреним вихідним файлам, SHA-256 яких записані "
        "в environment.json. Довгі рядки перенесено лише для верстки.")
    add("code", output.strip())
    add("h", "4. SQL створення БД та мінімальних даних")
    add("p", "SQLite створює файл БД під час відкриття з’єднання. SQL нижче "
        "створює її структуру та мінімальний набір записів для перевірок; "
        "виконувати ці скрипти потрібно в окремій порожній навчальній БД.")
    for name in env["sql_files"]:
        add("p", "Файл " + name)
        add("code", (ROOT / name).read_text().rstrip())
    add("h", "5. Повний лістинг тестів")
    add("p", "Файл " + env["test_file"])
    add("code", test_source.rstrip())
    add("h", "6. Висновок")
    add("p", f"У перевіреному наборі всі {summary[1]} тестів пройшли. "
        "Перевірено зв’язки двох рівнів master–detail, цілісність і бізнес-правила "
        "сховища та транзакційні сценарії, наведені в лістингу. Висновок стосується "
        "реалізованої SQLite-схеми й перевірених випадків; він не є оцінкою "
        "продуктивності багатокористувацького серверного розгортання.")
    return blocks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path,
                        default=Path("/System/Library/Fonts/Supplemental"))
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        "protocol_layout", HERE.parent / "unit_testing" / "build_protocol.py"
    )
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    renderer.HERE = HERE
    blocks = report_blocks()
    (HERE / "protocol.txt").write_text("\n\n".join(
        "\n".join(" | ".join(row) for row in value) if kind == "table" else value
        for kind, value in blocks if kind != "page"
    ) + "\n")
    renderer.build_docx(blocks, title=TITLE)
    renderer.build_pdf(blocks, args.font_dir, title=TITLE)
    print("Built database protocol: TXT, DOCX, PDF")
