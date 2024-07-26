import re
import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
import aiosqlite

BOT_TOKEN = 'token' # Тут токен вашего бота
CHANNEL_ID = -100id # Айди канала в который будут отправлятся посты. ВАЖНО: добавьте бота в канал, что бы отправлялись посты
OWNER_ID = id # Айди админа

DB_NAME = 'bot.db' 

BLACKLIST_FILE = 'blacklist.json' # Файл с айди пользователей, которые в чёрном списке, и не допускаются к отправке сообщений
BANWORDS_FILE = 'banwords.json' # Файл с запрещёнными словами. спец.символы не работают.

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

message_queue = asyncio.Queue()

async def execute_query(query, params=(), commit=False):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(query, params) as cursor:
            if commit:
                await conn.commit()
            return cursor

async def create_tables():
    create_users_table_query = '''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        chat_id INTEGER,
        is_owner INTEGER
    )
    '''
    create_restrictions_table_query = '''
    CREATE TABLE IF NOT EXISTS restrictions (
        chat_id INTEGER PRIMARY KEY,
        restriction_until TEXT
    )
    '''
    await execute_query(create_users_table_query, commit=True)
    await execute_query(create_restrictions_table_query, commit=True)

async def on_startup(dispatcher):
    await create_tables()
    print("Bot started, polling...")
    await dp.skip_updates()

def load_blacklist():
    try:
        with open(BLACKLIST_FILE, 'r', encoding='utf-8') as file:
            blacklist = json.load(file)
    except FileNotFoundError:
        blacklist = {"users": []}
    return blacklist

def save_blacklist(blacklist):
    with open(BLACKLIST_FILE, 'w', encoding='utf-8') as file:
        json.dump(blacklist, file, ensure_ascii=False, indent=4)

def is_user_blacklisted(user_id):
    blacklist = load_blacklist()
    for user in blacklist['users']:
        if user['id'] == user_id:
            return True
    return False

def get_blacklisted_user_info(user_id):
    blacklist = load_blacklist()
    for user in blacklist['users']:
        if user['id'] == user_id:
            return user
    return None

def add_to_blacklist(user_id, reason):
    blacklist = load_blacklist()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    blacklist['users'].append({
        "id": user_id,
        "reason": reason,
        "timestamp": now
    })
    save_blacklist(blacklist)

def contains_banned_words(text):
    banwords = load_banwords()
    for word in banwords['words']:
        if re.search(rf'\b{re.escape(word)}\b', text, flags=re.IGNORECASE):
            return True
    return False

def load_banwords():
    try:
        with open(BANWORDS_FILE, 'r', encoding='utf-8') as file:
            banwords = json.load(file)
    except FileNotFoundError:
        banwords = {"words": []}
    return banwords

def contains_banned_words(text):
    banwords = load_banwords()
    for word in banwords['words']:
        escaped_word = re.escape(word)
        escaped_word = escaped_word.replace(r'\ ', ' ')
        pattern = rf'\b{escaped_word}\b'
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False

@dp.message_handler(commands=['start'])
async def handle_start(message: types.Message):
    await message.reply("Привет! Я бот, в котором ты можешь отправить что-либо в канал.")

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
            await message.reply("Пожалуйста, ответьте на медиа-сообщение (фото, видео, GIF или стикер), чтобы использовать команду /media.")
    else:
        await message.reply("Пожалуйста, ответьте на медиа-сообщение (фото, видео, GIF или стикер), чтобы использовать команду /media.")

@dp.message_handler(commands=['unban'])
async def handle_unban(message: types.Message):
    if message.from_user.id == OWNER_ID:
        if len(message.text.split(maxsplit=1)) > 1:
            target = message.text.split(maxsplit=1)[1].strip('@')
            blacklist = load_blacklist()
            user_found = False
            for user in blacklist['users']:
                if user['id'] == target:
                    blacklist['users'].remove(user)
                    save_blacklist(blacklist)
                    user_found = True
                    await message.reply(f"@{target} был разбанен.")
                    break
            if not user_found:
                await message.reply("Пользователь не найден в черном списке.")
        else:
            await message.reply("Пожалуйста, укажите пользователя после команды /unban.")
    else:
        await message.reply("Вы не являетесь владельцем бота и не можете использовать команду /unban.")

@dp.message_handler(commands=['report'])
async def handle_report(message: types.Message):
    if len(message.text.split(maxsplit=1)) > 1:
        post_link = message.text.split(maxsplit=1)[1]
        report_reason = message.text.split(maxsplit=1)[2] if len(message.text.split(maxsplit=1)) > 2 else "Не указана"
        owner_message = (
            f"<b>Репорт:</b>\n"
            f"<a href='{post_link}'>Ссылка на пост</a>\n"
            f"<b>Причина репорта:</b> {report_reason}\n"
            f"<b>От кого репорт:</b> {message.from_user.get_mention(as_html=True)}"
        )
        await bot.send_message(OWNER_ID, owner_message, parse_mode=ParseMode.HTML)
        await message.reply("Спасибо за ваш репорт! Он был отправлен владельцу бота.")
    else:
        await message.reply("Пожалуйста, укажите ссылку на пост после команды /report.")

async def is_send_restricted(chat_id):
    query = 'SELECT * FROM restrictions WHERE chat_id = ?'
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(query, (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                restriction_until = row[1]
                if datetime.strptime(restriction_until, "%Y-%m-%d %H:%M:%S") > datetime.strptime(now, "%Y-%m-%d %H:%M:%S"):
                    return True
    return False

async def main():
    await on_startup(dp)
    await asyncio.gather(
        dp.start_polling(),
        message_worker()
    )

if __name__ == '__main__':
    asyncio.run(main())
