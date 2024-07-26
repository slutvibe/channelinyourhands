import os
import tempfile
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from bot import bot, dp, is_send_restricted, contains_banned_words, is_user_blacklisted, get_blacklisted_user_info, load_blacklist, load_banwords, save_blacklist, CHANNEL_ID

message_queue = asyncio.Queue()

async def message_worker():
    global message_queue
    while True:
        message_info = await message_queue.get()
        media_path, user_signature, media_type = message_info
        try:
            if media_type == 'photo':
                await bot.send_photo(CHANNEL_ID, photo=open(media_path, 'rb'), caption=user_signature, parse_mode=ParseMode.HTML)
            elif media_type == 'video':
                await bot.send_video(CHANNEL_ID, video=open(media_path, 'rb'), caption=user_signature, parse_mode=ParseMode.HTML)
            elif media_type == 'animation':
                await bot.send_animation(CHANNEL_ID, animation=open(media_path, 'rb'), caption=user_signature, parse_mode=ParseMode.HTML)
            elif media_type == 'sticker':
                await bot.send_sticker(CHANNEL_ID, sticker=open(media_path, 'rb'), caption=user_signature, parse_mode=ParseMode.HTML)
            os.remove(media_path)
        except Exception as e:
            print(f"Error sending media: {e}")
        finally:
            message_queue.task_done()

async def save_media_file(media, media_type):
    temp_dir = tempfile.gettempdir()
    file_info = await media.get_file()
    file_path = file_info.file_path
    temp_file_path = os.path.join(temp_dir, os.path.basename(file_path))
    await bot.download_file(file_path, temp_file_path)
    return temp_file_path

@dp.message_handler(commands=['send'])
async def handle_send(message: types.Message):
    if message.chat.type in ['supergroup', 'group', 'channel']:
        await message.reply("Команда /send поддерживается только в личных сообщениях с ботом.")
        return
    
    global message_queue
    if await is_send_restricted(message.from_user.id):
        await message.reply("Извините, отправка сообщений сейчас запрещена.")
    elif is_user_blacklisted(message.from_user.id):
        user_info = get_blacklisted_user_info(message.from_user.id)
        reason = user_info['reason']
        timestamp = user_info['timestamp']
        await message.reply(f"Вы были заблокированы.\nПричина: {reason}\nВремя, когда вы были заблокированы: {timestamp}")
    elif contains_banned_words(message.text):
        await message.reply("Ваше сообщение содержит запрещенные слова и не может быть отправлено в канал.")
    else:
        if len(message.text.split(maxsplit=1)) > 1:
            text_to_send = message.text.split(maxsplit=1)[1]
            await asyncio.sleep(2)
            user = message.from_user
            if user.username:
                user_mention = f"@{user.username}"
            else:
                user_mention = f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"
            user_signature = f"\nОтправлено пользователем: {user_mention}"
            try:
                await bot.send_message(CHANNEL_ID, text_to_send + user_signature, parse_mode=ParseMode.HTML)
                await message.reply("Текст успешно отправлен в канал.")
            except Exception as e:
                await message.reply(f"Произошла ошибка при отправке текста в канал: {e}")
        else:
            await message.reply("Пожалуйста, укажите текст после команды /send для отправки в канал.")

@dp.message_handler(commands=['media'])
async def handle_media(message: types.Message):
    if message.chat.type in ['supergroup', 'group', 'channel']:
        await message.reply("Команда /media поддерживается только в личных сообщениях с ботом.")
        return
    
    if await is_send_restricted(message.from_user.id):
        await message.reply("Извините, отправка сообщений сейчас запрещена.")
        return
    elif is_user_blacklisted(message.from_user.id):
        user_info = get_blacklisted_user_info(message.from_user.id)
        reason = user_info['reason']
        timestamp = user_info['timestamp']
        await message.reply(f"Вы были заблокированы.\nПричина: {reason}\nВремя, когда вы были заблокированы: {timestamp}")
        return
    elif message.reply_to_message:
        media = None
        media_type = None

        if message.reply_to_message.photo:
            media = message.reply_to_message.photo[-1]
            media_type = 'photo'
        elif message.reply_to_message.video:
            media = message.reply_to_message.video
            media_type = 'video'
        elif message.reply_to_message.animation:
            media = message.reply_to_message.animation
            media_type = 'animation'
        elif message.reply_to_message.sticker:
            media = message.reply_to_message.sticker
            media_type = 'sticker'

        if media:
            try:
                temp_file_path = await save_media_file(media, media_type)
                user = message.from_user
                if user.username:
                    user_mention = f"@{user.username}"
                else:
                    user_mention = f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"
                user_signature = f"\nОтправлено пользователем: {user_mention}"
                post_message = (temp_file_path, user_signature, media_type)
                await asyncio.sleep(2)
                await message_queue.put(post_message)
                await message.reply("Медиа будет отправлено в течение ближайших нескольких секунд.")
            except Exception as e:
                await message.reply(f"Произошла ошибка при загрузке медиа: {e}")
        else:
            await message.reply("Пожайлуста, ответьте на медиа-сообщение (фото, видео, GIF или стикер), чтобы использовать команду /media.")
    else:
        await message.reply("Пожалуйста, ответьте на медиа-сообщение (фото, видео, GIF или стикер), чтобы использовать команду /media.")
