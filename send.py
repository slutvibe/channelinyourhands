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

@dp.message_handler(content_types=['text', 'photo', 'video', 'animation', 'ticker'])
async def handle_message(message: types.Message):
    if message.chat.type in ['supergroup', 'group', 'channel']:
        return
    
    if await is_send_restricted(message.from_user.id):
        await message.reply("Извините, отправка сообщений сейчас запрещена.")
    elif is_user_blacklisted(message.from_user.id):
        user_info = get_blacklisted_user_info(message.from_user.id)
        reason = user_info['reason']
        timestamp = user_info['timestamp']
        await message.reply(f"Вы были заблокированы.\nПричина: {reason}\nВремя, когда вы были заблокированы: {timestamp}")
    else:
        user = message.from_user
        user_mention = f"<a href='tg://user?id={user.id}'>{user.full_name}</a> ({user.id})"
        user_signature = f"\nОтправлено пользователем: {user_mention}"

        if message.text:
            if contains_banned_words(message.text):
                await message.reply("Ваше сообщение содержит запрещенные слова и не может быть отправлено в канал.")
            else:
                try:
                    await bot.send_message(CHANNEL_ID, message.text + user_signature, parse_mode=ParseMode.HTML)
                    await message.reply("Ваше сообщение отправлено.")
                except Exception as e:
                    await message.reply(f"Произошла ошибка при отправке текста в канал: {e}")
        elif message.photo:
            media = message.photo[-1]
            media_type = 'photo'
            try:
                temp_file_path = await save_media_file(media, media_type)
                post_message = (temp_file_path, user_signature, media_type)
                await message_queue.put(post_message)
                await message.reply("Ваше сообщение отправлено.")
            except Exception as e:
                await message.reply(f"Произошла ошибка при загрузке медиа: {e}")
        elif message.video:
            media = message.video
            media_type = 'video'
            try:
                temp_file_path = await save_media_file(media, media_type)
                post_message = (temp_file_path, user_signature, media_type)
                await message_queue.put(post_message)
                await message.reply("Ваше сообщение отправлено.")
            except Exception as e:
                await message.reply(f"Произошла ошибка при загрузке медиа: {e}")
        elif message.animation:
            media = message.animation
            media_type = 'animation'
            try:
                temp_file_path = await save_media_file(media, media_type)
                post_message = (temp_file_path, user_signature, media_type)
                await message_queue.put(post_message)
                await message.reply("Ваше сообщение отправлено.")
            except Exception as e:
                await message.reply(f"Произошла ошибка при загрузке медиа: {e}")
        elif message.sticker:
            media = message.sticker
            media_type = 'ticker'
            try:
                temp_file_path = await save_media_file(media, media_type)
                post_message = (temp_file_path, user_signature, media_type)
                await message_queue.put(post_message)
                await message.reply("Ваше сообщение отправлено.")
            except Exception as e:
                await message.reply(f"Произошла ошибка при загрузке медиа: {e}")
                
@dp.message_handler(commands=['rules'])
async def handle_rules(message: types.Message):
    await message.reply("Правила Бота\n\nЗапрещена порнография\nЗапрещён спам\nЗапрещена реклама")

@dp.message_handler(commands=['help'])
async def handle_help(message: types.Message):
    await message.reply('Команды бота\n\n/help - Показать это сообщение\n/send "text" - Отправить текстовое сообщение в канал\n/media (ответ на фото, видео, стикер или GIF) - Отправить медиа в канал\n/report \'ссылка на пост\' \'причина репорта(по желанию)\' - Уведомить админа о нарушении')
