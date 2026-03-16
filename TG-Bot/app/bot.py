import asyncio
import logging
import subprocess
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_settings
from app.db import Database
from app.mtproto import MTProtoService


class MTProtoServerManager:
    def __init__(self, start_cmd: str | None) -> None:
        self.start_cmd = start_cmd
        self.process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        if not self.start_cmd:
            logging.info("MTPROTO_START_CMD is not set, assuming MTProto server already running")
            return
        logging.info("Starting MTProto server: %s", self.start_cmd)
        self.process = subprocess.Popen(self.start_cmd, shell=True)

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            logging.info("Stopping MTProto server process")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


load_dotenv()
settings = load_settings()
db = Database(settings.database_path)
mtproto = MTProtoService(settings.proxy_host, settings.proxy_port, settings.proxy_gen_cmd)
mtproto_server = MTProtoServerManager(settings.mtproto_start_cmd)


async def _ensure_user(message: Message) -> tuple[int, bool]:
    user = message.from_user
    assert user is not None
    is_admin = user.id in settings.admin_ids
    db.upsert_user(user.id, user.username, is_admin)
    return user.id, is_admin


def _admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:list_users")],
            [InlineKeyboardButton(text="🔑 Активные ключи", callback_data="admin:list_keys")],
            [InlineKeyboardButton(text="🧩 Выдать ключ себе", callback_data="admin:issue_self")],
        ]
    )


async def cmd_start(message: Message) -> None:
    _, is_admin = await _ensure_user(message)
    text = (
        "Привет! Я бот для продажи MTProto прокси.\n"
        "Команды:\n"
        "/get_proxy <device_id> — получить ключ для устройства\n"
        "/myid — показать ваш Telegram ID"
    )
    if is_admin:
        text += "\n/admin — открыть админ-панель"
    await message.answer(text)


async def cmd_myid(message: Message) -> None:
    user_id, _ = await _ensure_user(message)
    await message.answer(f"Ваш ID: {user_id}")


async def cmd_get_proxy(message: Message) -> None:
    user_id, _ = await _ensure_user(message)
    if not db.is_active_user(user_id):
        await message.answer("Ваш доступ отключён. Обратитесь к администратору.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        await message.answer(
            "Использование: /get_proxy <device_id>\n"
            "Пример: /get_proxy iphone_15_pro"
        )
        return

    device_id = parts[1].strip()
    if len(device_id) > 64:
        await message.answer("device_id слишком длинный (максимум 64 символа).")
        return

    user = db.get_user(user_id)
    if user and user.device_id and user.device_id != device_id:
        await message.answer(
            "Для вашего аккаунта уже привязано другое устройство.\n"
            f"Текущее устройство: `{user.device_id}`\n"
            "Обратитесь к администратору для сброса.",
            parse_mode="Markdown",
        )
        return

    db.bind_device(user_id, device_id)
    current_key = db.get_active_key(user_id)
    if current_key:
        await message.answer(
            "У вас уже есть активный ключ для устройства:\n"
            f"Устройство: `{current_key.device_id}`\n"
            f"Ключ: `{current_key.secret}`\n"
            f"Ссылка: {current_key.connection_uri}",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return

    secret, uri = mtproto.issue_key()
    db.create_proxy_key(user_id, device_id, secret, uri)
    await message.answer(
        "Ваш MTProto ключ:\n"
        f"Устройство: `{device_id}`\n"
        f"`{secret}`\n\n"
        "Ссылка для подключения:\n"
        f"{uri}",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_admin(message: Message) -> None:
    _, is_admin = await _ensure_user(message)
    if not is_admin:
        await message.answer("Недостаточно прав.")
        return
    await message.answer("Админ-панель", reply_markup=_admin_kb())


async def cmd_ban(message: Message) -> None:
    _, is_admin = await _ensure_user(message)
    if not is_admin:
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /ban <user_id>")
        return

    ok = db.set_user_status(int(parts[1]), False)
    await message.answer("Пользователь отключён." if ok else "Пользователь не найден.")


async def cmd_unban(message: Message) -> None:
    _, is_admin = await _ensure_user(message)
    if not is_admin:
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /unban <user_id>")
        return

    ok = db.set_user_status(int(parts[1]), True)
    await message.answer("Пользователь активирован." if ok else "Пользователь не найден.")


async def cmd_reset_device(message: Message) -> None:
    _, is_admin = await _ensure_user(message)
    if not is_admin:
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /reset_device <user_id>")
        return

    target_user_id = int(parts[1])
    db.bind_device(target_user_id, "")
    db.set_user_status(target_user_id, True)
    await message.answer("Привязка устройства сброшена. Пользователь может заново получить ключ.")


async def cb_admin(query: CallbackQuery) -> None:
    from_user = query.from_user
    if from_user.id not in settings.admin_ids:
        await query.answer("Недостаточно прав", show_alert=True)
        return

    action = query.data.split(":", 1)[1]
    if action == "list_users":
        users = db.list_users()
        if not users:
            text = "Пользователей пока нет."
        else:
            lines = [
                (
                    f"{u.user_id} (@{u.username or '-'}) | active={int(u.is_active)} "
                    f"| admin={int(u.is_admin)} | device={u.device_id or '-'}"
                )
                for u in users[:50]
            ]
            text = "\n".join(lines)
        await query.message.answer(text)
    elif action == "list_keys":
        keys = db.list_active_keys()
        if not keys:
            text = "Активных ключей нет."
        else:
            text = "\n".join(
                f"uid={k.user_id} | device={k.device_id} | key={k.secret}"
                for k in keys[:50]
            )
        await query.message.answer(text)
    elif action == "issue_self":
        user = db.get_user(from_user.id)
        device_id = user.device_id if user and user.device_id else "admin_device"
        db.bind_device(from_user.id, device_id)
        secret, uri = mtproto.issue_key()
        db.create_proxy_key(from_user.id, device_id, secret, uri)
        await query.message.answer(
            f"Ваш ключ:\nУстройство: `{device_id}`\n`{secret}`\n{uri}",
            parse_mode="Markdown",
        )

    await query.answer()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mtproto_server.start()

    bot = Bot(settings.bot_token)
    dp = Dispatcher()

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_myid, Command("myid"))
    dp.message.register(cmd_get_proxy, Command("get_proxy"))
    dp.message.register(cmd_admin, Command("admin"))
    dp.message.register(cmd_ban, Command("ban"))
    dp.message.register(cmd_unban, Command("unban"))
    dp.message.register(cmd_reset_device, Command("reset_device"))
    dp.callback_query.register(cb_admin, F.data.startswith("admin:"))

    try:
        await dp.start_polling(bot)
    finally:
        mtproto_server.stop()


if __name__ == "__main__":
    asyncio.run(main())