import asyncio
from aiogram import Dispatcher
from bot import create_tables, bot, dp
from send import message_worker

async def on_startup(dispatcher):
    await create_tables()
    print("Метро Люблино, работаем...")
    await dp.skip_updates()

async def main():
    await on_startup(dp)
    await asyncio.gather(
        dp.start_polling(),
        message_worker()
    )

if __name__ == '__main__':
    asyncio.run(main())