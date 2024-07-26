import re
import json
import aiosqlite
from datetime import datetime
import configparser
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode

DB_NAME = 'bot.db'
BLACKLIST_FILE = 'blacklist.json'
BANWORDS_FILE = 'banwords.json'

config = configparser.ConfigParser()
config.read('settings.ini')

BOT_TOKEN = config['bot']['token']
CHANNEL_ID = int(config['channel']['id'])
OWNER_ID = int(config['owner']['id'])

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

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
        escaped_word = re.escape(word)
        escaped_word = escaped_word.replace(r'\ ', ' ')
        pattern = rf'\b{escaped_word}\b'
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False

def load_banwords():
    try:
        with open(BANWORDS_FILE, 'r', encoding='utf-8') as file:
            banwords = json.load(file)
    except FileNotFoundError:
        banwords = {"words": []}
    return banwords

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