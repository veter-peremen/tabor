# Деплой на сервер (Linux / Timeweb)

Инструкция для Ubuntu/Debian VPS. Все команды — под root или через `sudo`.

## 1. Подготовка сервера

```bash
apt update
apt install -y python3 python3-venv python3-pip git sqlite3
```

Проверьте версию Python (нужен 3.11+):
```bash
python3 --version
```

## 2. Отдельный пользователь для бота (безопаснее, чем root)

```bash
useradd -r -m -d /opt/tabor -s /bin/bash tabor
```

## 3. Клонирование репозитория

```bash
cd /opt
git clone https://github.com/<ВАШ_ЛОГИН>/tabor.git tabor
chown -R tabor:tabor /opt/tabor
```

## 4. Виртуальное окружение и зависимости

```bash
sudo -u tabor bash -lc '
cd /opt/tabor
python3 -m venv .venv
./.venv/bin/pip install -U pip
./.venv/bin/pip install -r requirements.txt
'
```

## 5. Настройка .env

```bash
sudo -u tabor cp /opt/tabor/.env.example /opt/tabor/.env
sudo -u tabor nano /opt/tabor/.env
```

Заполните:
- `BOT_TOKEN` — токен от @BotFather;
- `SUPERADMIN_IDS` — ваш Telegram ID (можно несколько через запятую);
- `DB_PATH=events.db` (не меняйте — путь станет абсолютным внутри /opt/tabor);
- `PROXY` — **оставьте пустым**, если сервер видит Telegram напрямую (см. п. 6).

## 6. Проверка доступа к Telegram с сервера

```bash
sudo -u tabor /opt/tabor/.venv/bin/python -c "import socket; socket.create_connection(('api.telegram.org',443),timeout=6); print('Telegram доступен')"
```

- Печатает «Telegram доступен» → `PROXY` в `.env` оставляем пустым.
- `TimeoutError` → доступ закрыт, нужен прокси: пропишите `PROXY=socks5://user:pass@host:port`
  в `.env` и доустановите `./.venv/bin/pip install aiohttp-socks`.

## 7. Пробный запуск

```bash
sudo -u tabor bash -lc 'cd /opt/tabor && ./.venv/bin/python bot.py'
```

В логе должно появиться:
```
INFO | Авторизация успешна: @ваш_бот (id=...)
INFO | Бот запускается (long polling)...
```
Откройте бота в Telegram, отправьте `/start`. Остановите пробный запуск `Ctrl+C`.

## 8. Автозапуск через systemd

```bash
cp /opt/tabor/deploy/tabor-bot.service /etc/systemd/system/tabor-bot.service
systemctl daemon-reload
systemctl enable --now tabor-bot
systemctl status tabor-bot          # проверить, что active (running)
```

Логи в реальном времени:
```bash
journalctl -u tabor-bot -f
```

## 9. Автоматический бэкап БД

Копии кладутся в `/opt/tabor/backups`, хранятся последние 30.

```bash
chmod +x /opt/tabor/deploy/backup.sh
# разовая проверка:
sudo -u tabor /opt/tabor/deploy/backup.sh

# ежедневно в 03:00 — добавьте в crontab пользователя tabor:
sudo -u tabor crontab -e
# строка:
0 3 * * * /opt/tabor/deploy/backup.sh
```

Скачать бэкап к себе на машину (пример):
```bash
scp root@СЕРВЕР:/opt/tabor/backups/events-*.db.gz .
```

## 10. Обновление бота (выкатка новой версии)

```bash
cd /opt/tabor
sudo -u tabor git pull
sudo -u tabor ./.venv/bin/pip install -r requirements.txt   # если менялись зависимости
systemctl restart tabor-bot
```

## Важно про данные
- Файл `events.db` — это **живые данные** (мероприятия, пользователи). Он в `.gitignore`
  и **не** перезаписывается при `git pull`. Не удаляйте его.
- Схема БД мигрируется автоматически при старте (новые колонки/таблицы добавляются сами).
- Перед крупными обновлениями сделайте бэкап: `/opt/tabor/deploy/backup.sh`.

