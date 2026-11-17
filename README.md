# Infrastructure Lab API

Учебный production-like стенд для портфолио системного администратора и Python backend-разработчика.

## Состав

`Nginx → FastAPI → PostgreSQL`

- API не выставлено напрямую наружу: доступ только через Nginx.
- PostgreSQL находится во внутренней Docker-сети.
- `/health` проверяет доступность API, `/ready` — доступность API и PostgreSQL.
- Контейнер API запускается не от root-пользователя.
- Данные PostgreSQL хранятся в именованном Docker volume.

Подробная схема: [архитектура](docs/architecture.md). Действия при сбоях:
[runbook восстановления](docs/runbook.md).

## Первый запуск

1. Скопируйте `.env.example` в `.env`.
2. Замените тестовый пароль в `.env` на свой локальный пароль.
3. Выполните:

```powershell
docker compose up --build -d
```

4. Проверьте:

```powershell
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/ready
docker compose ps
```

Swagger будет доступен по `http://localhost:8080/docs`.

## Мониторинг

Prometheus собирает метрики API, контейнеров и PostgreSQL каждые 15 секунд. Панель доступна только с этого компьютера:

- `http://localhost:9090/targets` — статус сборщиков метрик;
- `http://localhost:9090/graph` — графики и PromQL-запросы.

Полезные первые запросы:

```text
up
rate(http_requests_total[5m])
container_memory_usage_bytes
```

### Правила реагирования

Prometheus автоматически проверяет четыре условия и показывает активные
срабатывания на `http://localhost:9090/alerts`:

- API недоступно более минуты;
- метрики PostgreSQL недоступны более минуты;
- доля HTTP 5xx выше 5% в течение пяти минут;
- p95 времени ответа API выше одной секунды в течение пяти минут.

Правила хранятся в `prometheus/rules/infrastructure.yml`. Это безопасная
локальная основа для мониторинга.

## Telegram-уведомления

Alertmanager передаёт срабатывания внутреннему сервису, который отправляет их
в Telegram. Добавьте в **локальный** `.env` (не в `.env.example`) два значения:

```text
TELEGRAM_BOT_TOKEN=<новый токен BotFather>
TELEGRAM_CHAT_ID=<идентификатор личного чата или группы>
```

После этого перезапустите сервисы:

```powershell
docker compose up -d --build
```

Веб-интерфейс Alertmanager доступен только с этого компьютера:
`http://localhost:9093`. Токен не записывается в репозиторий и не выводится
в логах. До заполнения двух переменных уведомления не отправляются.

## Grafana

Grafana доступна только с этого компьютера: `http://localhost:3000`.

Начальные учётные данные для локального стенда: `admin` / `admin`. После первого
входа Grafana попросит задать новый пароль. Дашборд **Infrastructure Lab Overview**
создаётся автоматически и показывает доступность API и PostgreSQL, поток запросов,
время ответа p95, потребление памяти контейнерами и количество подключений к БД.

## CI

В `.github/workflows/ci.yml` настроен GitHub Actions. При каждом push и pull request он:

1. запускает Ruff и pytest;
2. проверяет Docker Compose-конфигурацию;
3. собирает и запускает ключевые сервисы Docker Compose;
4. проверяет `/health`, `/ready` API, Prometheus, Alertmanager, Grafana и
   внутренний сервис Telegram-уведомлений.

Локальная проверка перед публикацией:

```powershell
python -m pip install -r requirements-dev.txt
$env:DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/test"
ruff check app tests
pytest -q
```

## Учёт инцидентов

API содержит небольшой, но практический модуль учёта инцидентов: он помогает
зафиксировать проблему, назначить приоритет и провести её по статусам
`open → investigating → resolved`.

Доступные операции в Swagger:

- `POST /incidents` — зарегистрировать инцидент;
- `GET /incidents` — показать список, сначала незакрытые;
- `PATCH /incidents/{id}/status` — изменить статус обработки.

Таблица `incidents` создаётся автоматически при старте API. Это позволяет
показать в проекте не только инфраструктуру, но и работу backend-приложения с
PostgreSQL: запись, чтение, валидацию данных и обработку ошибок.

## Резервное копирование и проверка восстановления

Создать backup PostgreSQL в формате `pg_dump`:

```powershell
.\scripts\backup-postgres.ps1
```

Скрипт хранит последние 14 копий в папке `backups/`, которая не попадёт в Git. Пароль базы не выводится и не сохраняется в команде backup.

Проверить, что последняя резервная копия действительно восстанавливается:

```powershell
.\scripts\test-restore.ps1
```

Проверка создаёт отдельную тестовую БД `infra_lab_restore_check`, восстанавливает в неё последнюю копию и выполняет запрос проверки. Рабочая БД `infra_lab` не изменяется.

## Дальше

1. Добавить сканирование Docker-образов и зависимостей на уязвимости.
2. Настроить внешнее, зашифрованное хранение резервных копий.
