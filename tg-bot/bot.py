import asyncio

import httpx
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from config import bot_settings

dp = Dispatcher()
bot = Bot(token=bot_settings.token)
lock = asyncio.Lock()


# Command handler
@dp.message(Command("start"))
async def command_start_handler(message: Message) -> None:
    if (
        not message.from_user
    ) or message.from_user.username not in bot_settings.whitelist:
        return

    await message.answer("Hello! I'm a bot created with aiogram.")


@dp.message(Command("reindex"))
async def command_reindex_handler(message: Message) -> None:
    if (
        not message.from_user
    ) or message.from_user.username not in bot_settings.whitelist:
        return

    await lock.acquire()
    try:
        msg = await message.answer(
            "⏳️ Запущено обновление векторного хранилища, это займёт какое-то время. Не посылайте новых запросов до завершения операции."
        )

        async with httpx.AsyncClient() as client:
            await client.post(
                bot_settings.reindex_url,
                json={
                    "request": message.text,
                    "session": message.chat.id,
                    "user": message.from_user.id,
                },
                timeout=60.0,
            )
    finally:
        lock.release()

    await msg.edit_text("✅ Векторное хранилище обновлено!")


@dp.message()
async def echo_handler(message: Message):
    if (
        not message.from_user
    ) or message.from_user.username not in bot_settings.whitelist:
        return

    await lock.acquire()

    msg = await message.answer("🧠 Думаю...")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                bot_settings.invoke_url,
                json={
                    "request": message.text,
                    "session": message.chat.id,
                    "user": message.from_user.id,
                },
                timeout=60.0,
            )
            try:
                resp.raise_for_status()
                ans = resp.json()
            #            await message.answer(resp.json().get("text", "--NOANSWER--"))
            except httpx.HTTPStatusError as e:
                await msg.edit_text(f"Request to agent failed: {type(e)} {e}")
                return

            if "error" in ans:
                await msg.edit_text(f"Agent returned error: {ans['error']}")
                return

            if "text" not in ans:
                await msg.edit_text(f"No answer from agent, and no error")
                return

        await msg.edit_text(ans["text"])
    finally:
        lock.release()


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
