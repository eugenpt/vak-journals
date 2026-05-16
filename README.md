# vak-journals

Скрипты для работы с **Перечнем рецензируемых научных изданий** (диссертации, кандидат/доктор наук).

**По состоянию на 10.04.2026 г.** — как в официальном PDF.

> Неофициальная автоматическая выгрузка. Для решений по публикациям используйте [официальный PDF](SOURCE_URL.txt) на сайте ВАК.

## Источник PDF

В [`SOURCE_URL.txt`](SOURCE_URL.txt) — **одна строка** (удобно copy-paste): HTTPS-ссылка **или** путь к локальному файлу. Строки с `#` — подсказки.

Актуальную ссылку возьмите на странице официальных документов:  
**https://vak.gisnauka.ru/documents/editions**  
(откройте PDF «Перечень рецензируемых научных изданий…» и скопируйте URL из браузера).

Примеры в `SOURCE_URL.txt`:

```text
https://vak.gisnauka.ru/s3-files/.../....pdf
D:\Downloads\peer_reviewed_journals.pdf
```

- **URL** — `download.py` сохраняет копию в `data/` (в git не коммитится).
- **Локальный путь** — скрипты читают файл напрямую; `download.py` только проверяет наличие (или копирует в `data/` с `--force`).

## Установка

```bash
cd vak-journals
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Скрипты

| Скрипт | Назначение |
|--------|------------|
| `download.py` | Скачать PDF по URL из `SOURCE_URL.txt` или проверить локальный путь |
| `extract_journals.py` | PDF → `output/journals.xlsx` |
| `parse_structured.py` | PDF → `output/journals_structured.xlsx` (журналы, специальности, связи, даты) |
| `build.py` | Всё сразу |

```bash
python download.py
python build.py --download
```

По отдельности:

```bash
python extract_journals.py --pdf data/vak_peer_reviewed_journals.pdf
python parse_structured.py --pdf data/vak_peer_reviewed_journals.pdf
```

Общие пути и дата актуальности — в `config.py`.

## Выходные файлы

- `output/journals.xlsx` — плоская таблица журналов
- `output/journals_structured.xlsx` — листы **Journals**, **Specialties**, **Journal_Spec_Map**, **Parse_Summary**

На листе **Journal_Spec_Map**: `date_from` (`с …`), `date_to` (`по …`), `group_index` (группа специальностей с одними датами).

## Обновление перечня

1. На [vak.gisnauka.ru/documents/editions](https://vak.gisnauka.ru/documents/editions) скопируйте ссылку на новый PDF в `SOURCE_URL.txt` (одной строкой).
2. При необходимости обновите `AS_OF_DATE` в `config.py`.
3. `python download.py --force` (для URL) или укажите локальный путь к скачанному PDF.
4. `python build.py`

## Структура

```
vak-journals/
├── README.md
├── SOURCE_URL.txt
├── config.py
├── download.py
├── extract_journals.py
├── parse_structured.py
├── build.py
├── requirements.txt
├── data/      # PDF (gitignored)
└── output/    # XLSX (gitignored)
```

`parse_structured.py` импортирует разбор журналов из `extract_journals.py` — отдельный пакет не нужен: это один репозиторий-утилита из нескольких файлов.

## Лицензия

Код репозитория — [MIT](LICENSE).

Текст **Перечня рецензируемых научных изданий** — официальный документ ВАК; права на него принадлежат правообладателю. Этот проект не аффилирован с ВАК и не заменяет официальный PDF на [vak.gisnauka.ru](https://vak.gisnauka.ru/documents/editions).
