# Infrastructure Lab API

Учебный production-like стенд для портфолио системного администратора и Python backend-разработчика.

## Состав

`Nginx → FastAPI → PostgreSQL`

- API не выставлено напрямую наружу: доступ только через Nginx.
- PostgreSQL находится во внутренней Docker-сети.
- `/health` проверяет доступность API, `/ready` — доступность API и PostgreSQL.
- Контейнер API запускается не от root-пользователя.
- Данные PostgreSQL хранятся в именованном Docker volume.

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

Prometheus собирает метрики API и контейнеров каждые 15 секунд. Панель доступна только с этого компьютера:

- `http://localhost:9090/targets` — статус сборщиков метрик;
- `http://localhost:9090/graph` — графики и PromQL-запросы.

Полезные первые запросы:

```text
up
rate(http_requests_total[5m])
container_memory_usage_bytes
```

## CI

В `.github/workflows/ci.yml` настроен GitHub Actions. При каждом push и pull request он:

1. запускает Ruff и pytest;
2. проверяет Docker Compose-конфигурацию;
3. собирает Docker-образ API.

Локальная проверка перед публикацией:

```powershell
python -m pip install -r requirements-dev.txt
$env:DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/test"
ruff check app tests
pytest -q
```

## Следующие этапы

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

1. GitHub Actions: линтер, тесты и сборка контейнера.
2. Документация по восстановлению после сбоя.
