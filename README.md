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
| `build.py` | Всё сразу (XLSX + `docs/data/vak.json` для сайта) |
| `fetch_scopus.py` | Batch-фетч Scopus данных (SJR, SNIP, CiteScore) через Elsevier API, кеширование |
| `fetch_rcsi.py` | Batch-фетч данных РЦНИ (уровень, даты) через journalrank.rcsi.science, кеширование |

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

## Сайт (GitHub Pages)

Статический поиск в каталоге `docs/`: журнал → специальности с датами и обратно, фильтр «актуально на дату».

После `python build.py --download` откройте локально:

```bash
cd docs
python -m http.server 8080
```

→ http://localhost:8080

Публикация: в настройках репозитория включите **Pages → Source: GitHub Actions**. При push в `main` workflow собирает JSON из PDF и деплоит `docs/`.

Сайт: **https://eugenpt.github.io/vak-journals/**

`python build.py` также обновляет `docs/sitemap.xml`. Пока сайт остаётся single-page app, sitemap содержит только главную страницу: query-ссылки на журналы и специальности не добавляются, чтобы не рекламировать поисковикам тысячи URL с одним и тем же исходным HTML. `robots.txt` уже указывает поисковикам на этот sitemap.

При сборке JSON дополнительно подтягиваются ссылки на **паспорта научных специальностей** из официального ВАК ([vak.gisnauka.ru -> news type 17](https://vak.gisnauka.ru/api/news/news-list/?page=1&pageSize=10&type=17)) и добавляются в карточки специальностей, если код специальности найден в текущей номенклатуре.

### Белый список РЦНИ

В карточке журнала отображается блок **Белый список РЦНИ**: уровень (2023/2025), даты включения/исключения, ссылка на карточку. Данные фетчатся один раз при сборке через [`fetch_rcsi.py`](fetch_rcsi.py) и встраиваются в `vak.json` — без Cloudflare Worker.

### Scopus

В карточке журнала отображается блок **Scopus**: CiteScore, SJR, SNIP, ссылка на карточку источника. Данные фетчатся один раз при сборке через [`fetch_scopus.py`](fetch_scopus.py) и встраиваются в `vak.json` — никаких live-запросов из браузера.

Для работы нужен **бесплатный API-ключ Elsevier** (регистрация на [dev.elsevier.com](https://dev.elsevier.com), ~5000 запросов/неделю).

Ключ хранится в GitHub Actions secret `SCOPUS_API_KEY`. При локальной сборке задать через переменную окружения:

```bash
set SCOPUS_API_KEY=ваш_ключ
python build.py --download
```

Или положить ключ (одной строкой) в `.scopus_key` (файл в `.gitignore`) и запустить `run_local.bat`:

```bash
run_local.bat
```

Скрипт кеширует результаты в `data/scopus_cache.json` (не коммитится) — при повторном билде перезапрашиваются только новые ISSN. Фетчит параллельно (6 потоков, укладываясь в лимит API 6 запросов/с) — ~9 минут на все ISSN.

### Статистика (Яндекс.Метрика)

Для русскоязычной аудитории Метрика уместнее Google Analytics: визиты, поисковые запросы, карта кликов.

1. [metrika.yandex.ru](https://metrika.yandex.ru/) → добавить счётчик для URL сайта.
2. Вставить предложенный Яндексом код счётчика в начало `<body>` в [`docs/index.html`](docs/index.html).
3. Закоммитить и задеплоить.

В текущей версии счётчик уже добавлен в HTML напрямую.

Без Метрики вы всё равно видите только факт деплоя в GitHub Actions; числа посетителей без аналитики не видны.

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
├── export_json.py
├── fetch_scopus.py      # Scopus данные через Elsevier API
├── fetch_rcsi.py        # РЦНИ данные (журналrank.rcsi.science)
├── run_local.bat        # Локальная сборка (Windows)
├── requirements.txt
├── docs/              # GitHub Pages (index.html, data/vak.json)
├── .github/workflows/ # pages.yml
├── data/              # PDF (gitignored)
└── output/            # XLSX (gitignored)
```

`parse_structured.py` импортирует разбор журналов из `extract_journals.py` — отдельный пакет не нужен: это один репозиторий-утилита из нескольких файлов.

## Лицензия

Код репозитория — [MIT](LICENSE).

Текст **Перечня рецензируемых научных изданий** — официальный документ ВАК; права на него принадлежат правообладателю. Этот проект не аффилирован с ВАК и не заменяет официальный PDF на [vak.gisnauka.ru](https://vak.gisnauka.ru/documents/editions).
