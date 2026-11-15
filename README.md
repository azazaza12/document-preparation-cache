# document-preparation

Кэширующие декораторы хранилищ и стратегии подготовки формата для конвейеров
обработки документов.

Зависит от стандартной библиотеки Python и `filetype`. Интеграция с
приложением — через порты.

## Задача

Конвейер обработки документов принимает файлы в произвольных форматах:
`pdf`, `doc`, `docx`, `odt`, `rtf`, `xls`, `xlsx`, `ods`. Дальше по
конвейеру работают инструменты, понимающие только `pdf`, `docx` и `xlsx`,
поэтому файл нужно заранее привести к пригодному формату.

Конвертация через LibreOffice/UNO стоит секунды, а конвейер перезапускается:
повторная обработка, переизвлечение полей, отладка. Библиотека решает две
связанные задачи — выбрать нужное преобразование по фактическому типу файла
и не выполнять его дважды.

## Устройство

```
src/document_preparation/
├── content.py          типы содержимого документа
├── ports.py            интерфейсы хранилища, стратегии, конвертера и рендерера
├── strategies.py       стратегии подготовки и маршрутизация
├── cached.py           кэширующие декораторы хранилищ
├── uno.py              адаптер к unoserver
└── uno_subprocess.py   вызов unoconvert
```

### Кэш как декоратор хранилища

`CachedPreparedDocumentStorage` реализует тот же `IDocumentStorage`, что и
обычное хранилище, поэтому вставляется в конвейер без изменений вызывающего
кода. Промах кэша определяется не флагом, а исключением
`DocumentNotFoundError` от нижнего хранилища:

```python
async def get(self, document: Document) -> PreparedDocumentContent:
    try:
        cached = await self._prepared_storage.get(document)
    except DocumentNotFoundError:
        raw = await self._raw_storage.get(document)
        extension = _guess_extension(raw.content)
        prepared = await self._strategy.prepare(document, raw.content, extension)
        await self._prepared_storage.set(...)
        return prepared
    extension = _guess_extension(cached.content)
    return PreparedDocumentContent(
        content=cached.content,
        file_name=self._strategy.resolve_file_name(document, extension),
    )
```

При попадании в кэш имя файла пересчитывается заново, а не берётся из
хранилища: байты уже подготовлены, но вызывающему коду нужно корректное
расширение.

`CachedMarkdownStorage` устроен так же для другой пары: если markdown для
документа ещё не построен, он рендерится из промежуточного представления и
кладётся в кэш.

### Маршрутизация по фактическому типу файла

Расширение определяется по содержимому (`filetype.guess`), а не по имени
файла: пользователь загружает `договор.pdf`, внутри которого `docx`.

Стратегия объявляет, какие исходные форматы принимает и к какому приводит:

```python
class PreparedTextStrategy(BasePreparedStrategy):
    _source_extensions = frozenset({".pdf", ".doc", ".docx", ".odt", ".rtf"})
    _target_suffix = ".docx"


class PreparedSpreadsheetStrategy(BasePreparedStrategy):
    _source_extensions = frozenset({".xls", ".xlsx", ".ods"})
    _target_suffix = ".xlsx"
```

`PreparedStrategyMapper` сам реализует `IPreparedStrategy` и выбирает
подходящую стратегию через `supports()`. Хранилище не знает, работает оно с
одной стратегией или с набором. Если формат не поддерживается, маппер
поднимает ошибку, а не возвращает файл без преобразования.

Форматы, уже пригодные для дальнейшей обработки, конвертер не трогает:
`docx` на входе остаётся `docx`, конвертация пропускается.

## Пример

```python
from document_preparation import (
    CachedPreparedDocumentStorage,
    ConversionTarget,
    PreparedSpreadsheetStrategy,
    PreparedStrategyMapper,
    PreparedTextStrategy,
    UnoConverter,
    UnoConverterSettings,
)

settings = UnoConverterSettings(UNO_HOST="unoserver", UNO_PORT=2003)
mapper = PreparedStrategyMapper(
    [
        PreparedSpreadsheetStrategy(UnoConverter(settings, ConversionTarget.XLSX)),
        PreparedTextStrategy(UnoConverter(settings, ConversionTarget.DOCX)),
    ]
)

storage = CachedPreparedDocumentStorage(prepared_storage, raw_storage, mapper)
prepared = await storage.get(document)
```

## Разработка

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy src
```

Python 3.14, `mypy --strict` без замечаний.

## Происхождение кода

Модуль выделен из закрытого проекта автоматизации проверки закупочной
документации, с разрешения правообладателя. Перенесена история коммитов
только относящихся к нему файлов, поэтому в `git log` есть коммиты других
участников команды. Их коммиты сохранены, но имена и адреса заменены на
`Contributor A/B`, чтобы не публиковать персональные данные без согласия.

История охватывает май-июнь 2026 года: сначала кэширование markdown, затем
кэш подготовленных документов, затем переход от маршрутизации по типу
документа к маршрутизации по фактическому расширению файла. Коммиты,
не затрагивавшие эти файлы, в историю не попали.

Это командный код. Базовые типы содержимого (`content.py`) и интерфейс
хранилища (`IDocumentStorage` в `ports.py`) написаны коллегой и включены
потому, что без них модуль не работает. Остальное — около 95% строк текущего среза — моё:
кэширующие декораторы, стратегии подготовки и маршрутизация, определение
формата по содержимому, адаптер к unoserver и все тесты.

При выделении удалены привязки к инфраструктуре исходного приложения:
клиент объектного хранилища MinIO (написан коллегой), брокер задач, система
конфигурации, зависимость от конкретной библиотеки разбора документов.
Хранилища и рендерер markdown заменены на порты, конкретный тип документа —
на протокол с `id` и `file_name`.

## Условия использования

Репозиторий опубликован как демонстрация инженерных решений, а не как
библиотека для повторного использования. Файл лицензии отсутствует:
исключительные права на исходный проект принадлежат заказчику, часть строк
написана другими участниками команды. Разрешение на копирование, изменение
и распространение не предоставляется.
