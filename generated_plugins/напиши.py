from aiogram import types, Bot, Dispatcher
from aiogram.filters import Command

def register_plugin(dp: Dispatcher, bot: Bot, admin_id: int):
    @dp.message(Command('sex'))
    async def my_handler(message: types.Message):
        if message.from_user.id != admin_id:
            return
        await message.answer('нахуй')