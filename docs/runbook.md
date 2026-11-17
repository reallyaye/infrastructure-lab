# Runbook: восстановление Infrastructure Lab

## Первичная проверка

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/ready
```

Панели для диагностики:

- Prometheus: `http://localhost:9090/targets` и `http://localhost:9090/alerts`;
- Grafana: `http://localhost:3000`;
- Alertmanager: `http://localhost:9093`.

## API недоступно или Nginx возвращает 502

```powershell
docker compose logs --tail 100 api nginx
docker compose up -d --build api nginx
```

Nginx использует встроенный DNS Docker и повторно определяет адрес API после
пересоздания контейнера. Если 502 не исчезает, проверьте статус API и базу через
`/ready` до повторного запуска Nginx.

## PostgreSQL недоступна

```powershell
docker compose logs --tail 100 database
docker compose up -d database
```

После восстановления БД проверьте `/ready` и Prometheus target `postgresql`.
Не удаляйте Docker volume `postgres_data`, пока не подтверждены восстановление
и актуальность резервной копии.

## Резервная копия и восстановление

Создать резервную копию:

```powershell
.\scripts\backup-postgres.ps1
```

Проверить восстановление последней копии в отдельную БД:

```powershell
.\scripts\test-restore.ps1
```

Скрипт проверки не изменяет рабочую БД. Перед реальным восстановлением нужно
остановиться и определить точную требуемую точку восстановления.

## Уведомления не приходят

```powershell
docker compose logs --tail 100 alertmanager telegram-notifier
docker compose up -d --force-recreate telegram-notifier
```

Убедитесь, что в локальном `.env` заданы `TELEGRAM_BOT_TOKEN` и
`TELEGRAM_CHAT_ID`, а пользователь нажал `/start` в нужном боте. Не публикуйте
содержимое `.env` или вывод с токеном.
