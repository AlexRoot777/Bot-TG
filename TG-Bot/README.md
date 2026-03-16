# Bot-TG
123123

Телеграм-бот на Python для продажи MTProto-прокси:

- при старте бота можно автоматически поднимать MTProto сервис на сервере;
- выдаёт пользователю MTProto-ключ и `tg://` ссылку подключения;
- есть админ-панель для контроля пользователей, устройств и активных ключей;
- включено ограничение: **один пользователь = одно устройство = один активный ключ**.

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Создайте `.env`:

```env
BOT_TOKEN=ваш_токен_бота
ADMIN_IDS=123456789,987654321

# Внешний IP/домен MTProto сервера (войдёт в tg:// ссылку)
PROXY_HOST=your.server.ip
PROXY_PORT=443

DATABASE_PATH=bot.db

# Генерация секрета на сервере (опционально)
PROXY_GEN_CMD=/workspace/Bot-TG/scripts/generate_mtproto_secret.sh

# Команда запуска MTProto сервера при старте бота (опционально)
# Пример: MTPROTO_START_CMD="docker compose -f /opt/mtproto/docker-compose.yml up -d"
MTPROTO_START_CMD=
```

Запуск:

```bash
python bot.py
```

## Как это работает

### 1) Автозапуск MTProto на сервере

Если `MTPROTO_START_CMD` задана, бот выполнит эту команду при старте.

Примеры:

```env
MTPROTO_START_CMD="systemctl start mtproto-proxy"
```

или

```env
MTPROTO_START_CMD="docker compose -f /opt/mtproto/docker-compose.yml up -d"
```

Если переменная пустая — бот считает, что MTProto уже запущен отдельно.

### 2) Выдача ссылки подключения

При `/get_proxy <device_id>` бот возвращает:

- секрет,
- готовую ссылку `tg://proxy?server=...&port=...&secret=...`

### 3) Ограничение «1 ключ = 1 пользователь = 1 устройство»

- Пользователь обязан запросить ключ как `/get_proxy <device_id>`.
- Первый `device_id` закрепляется за пользователем.
- Если пользователь попытается запросить ключ для другого `device_id`, бот откажет.
- У пользователя хранится только один активный ключ.

Админ может сбросить устройство пользователя командой `/reset_device <user_id>`.

## Откуда взять `PROXY_GEN_CMD`

`PROXY_GEN_CMD` — это путь к исполняемому скрипту на сервере, где работает бот.

Готовый пример уже есть в репозитории:

- `scripts/generate_mtproto_secret.sh`

Можно использовать напрямую:

```env
PROXY_GEN_CMD=/workspace/Bot-TG/scripts/generate_mtproto_secret.sh
```

Либо установить в системный путь:

```bash
sudo cp /workspace/Bot-TG/scripts/generate_mtproto_secret.sh /usr/local/bin/generate_mtproto_secret
sudo chmod +x /usr/local/bin/generate_mtproto_secret
```

И затем:

```env
PROXY_GEN_CMD=/usr/local/bin/generate_mtproto_secret
```

## Команды бота

Пользователь:

- `/start`
- `/myid`
- `/get_proxy <device_id>` — получить/показать активный ключ для закреплённого устройства

Админ:

- `/admin` — открыть inline-панель
- `/ban <user_id>` — отключить пользователя
- `/unban <user_id>` — включить пользователя
- `/reset_device <user_id>` — сбросить привязку устройства пользователя
- в админ-панели доступны списки пользователей и активных ключей