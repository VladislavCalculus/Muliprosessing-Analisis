# Практична робота: тестування реляційної БД

Навчальна БД зберігає історію пакетного аудіоаналізу:
`analysis_run → file_result → spectral_peak` — два послідовні зв'язки
master–detail. `result_store` є окремим backend-пакетом; MLT-3 буде вебінтерфейсом
і не потрібен для виконання DB-перевірок.

Фактичний прогін 2026-11-24: **9 DB-тестів пройшли за 1,51 с**;
повна регресія — **45 тестів за 24,20 с**. Незалежний review SQLite/CLI
пройшов без відкритих зауважень. Протокол PDF має 9 сторінок, включаючи
повні SQL-скрипти й тестовий код.

## SQL і перевірки

SQL структури та мінімальних даних знаходиться у `src/result_store/schema.sql`
і `src/result_store/seed.sql`. Для окремої порожньої навчальної БД:

```sh
sqlite3 /tmp/audio-analysis-coursework.sqlite < src/result_store/schema.sql
sqlite3 /tmp/audio-analysis-coursework.sqlite < src/result_store/seed.sql
```

Кожен pytest-сценарій використовує окрему тимчасову БД. З кореня проєкту:

```sh
PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider test/test_result_store.py -v
```

`pytest.txt` містить фактичний вивід перевірок, `environment.json` — версії
та SHA-256 перевірених файлів. Протокол включає повні SQL-скрипти й тести:
[PDF](protocol.pdf), [DOCX](protocol.docx), [TXT](protocol.txt).

Повторне збереження доказів (у `--date` вказати дату фактичного прогону):

```sh
.venv/bin/python docs/database_testing/run_evidence.py --date YYYY-MM-DD --full
```

## Повторне формування протоколу

```sh
.venv/bin/python -m pip install -r docs/unit_testing/requirements-report.txt
.venv/bin/python docs/database_testing/build_protocol.py
```

PDF використовує Arial.ttf, Arial Bold.ttf і Courier New.ttf. Типовий каталог —
`/System/Library/Fonts/Supplemental`; інший можна передати через `--font-dir`.
Оформлення спільне з попереднім протоколом модульного тестування. Генератор
читає збережені докази, перевіряє хеші й не запускає pytest. Після змін схеми
або коду потрібно повторити перевірки та оновити докази перед генерацією.

SQLite підтримує реляційні зв'язки, обмеження та тригери, але не звичайні
SQL-збережені процедури `CREATE PROCEDURE/CALL`. Протокол не заявляє їх
реалізованими. Якщо окрема така процедура обов'язкова за критеріями викладача,
цей пункт потребуватиме іншої СУБД; Python-метод не вважається її заміною.
