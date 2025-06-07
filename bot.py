import logging
import asyncio
import re
import os
import json
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher
from aiogram.types import Message, ChatPermissions, ChatMemberAdministrator, ChatMemberOwner
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.bot import DefaultBotProperties

API_TOKEN = '8076308761:AAGRQ1txwjZnjsquWrpeVGEAb7TqkDKsim4'

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

WARN_FILE = 'warns.json'

if os.path.exists(WARN_FILE):
    with open(WARN_FILE, 'r', encoding='utf-8') as f:
        user_warns = json.load(f)
        user_warns = {int(k): int(v) for k, v in user_warns.items()}
else:
    user_warns = {}

def save_warns():
    with open(WARN_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_warns, f, ensure_ascii=False)

def build_user_link(name, user_id):
    return f'<a href="tg://user?id={user_id}">{name}</a>'

def parse_duration(text):
    text = text.strip().lower()
    units_map = {
        'минут': 'minutes', 'мин': 'minutes', 'м': 'minutes',
        'час': 'hours', 'ч': 'hours',
        'день': 'days', 'д': 'days',
        'неделя': 'weeks', 'н': 'weeks',
        'месяц': 'days'  # считается как 30 дней
    }
    match = re.match(r'(\d+)\s*(\D+)', text)
    if not match:
        return None
    val, unit_raw = match.groups()
    val = int(val)
    for key in units_map:
        if unit_raw.startswith(key):
            unit = units_map[key]
            if 'месяц' in key:
                return timedelta(days=val * 30)
            return timedelta(**{unit: val})
    return None

async def can_restrict_member(chat_id: int, user_id: int):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception as e:
        logging.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
        return False
    if isinstance(member, ChatMemberOwner):
        return False
    if isinstance(member, ChatMemberAdministrator) and member.can_restrict_members is False:
        return False
    return True

async def mute_user(chat_id, user_id, duration: timedelta, reason: str, user_name: str):
    until = datetime.now(timezone.utc) + duration
    try:
        await bot.restrict_chat_member(
            chat_id,
            user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )
        await bot.send_message(chat_id, f"🔇 {build_user_link(user_name, user_id)} замучен на {duration}.\nПричина: {reason}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Ошибка при муте: {e}")

async def unmute_user(chat_id, user_id, user_name):
    try:
        await bot.restrict_chat_member(
            chat_id,
            user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
            ),
            until_date=None
        )
        await bot.send_message(chat_id, f"✅ {build_user_link(user_name, user_id)} размучен.", parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Ошибка при размуте: {e}")

async def warn_user(chat_id, user_id, user_name, reason, message: Message):
    warns = user_warns.get(user_id, 0) + 1
    user_warns[user_id] = warns
    save_warns()
    await message.reply(f"⚠️ {build_user_link(user_name, user_id)} получил предупреждение №{warns}.\nПричина: {reason}", parse_mode=ParseMode.HTML)

USER_MESSAGE_HISTORY = {}
SPAM_LIMIT = 10
SPAM_TIME_SECONDS = 30

RACIAL_SLURS = [
    r"\bнегр(ы|а|ов|е|ом)?\b",
    r"пидорас(ы|а|ов|е|ом)?",
    r"чмо",
    r"шалава",
    r"шлюха",
    r"дибил",
    r"долбоёб",
    r"даун",
    r"тварь ебаная",
    r"пизда",
    r"хуесос",
    r"говноед",
    r"пиздобол",
    r"блядина",
    r"попрошайник",
    r"попрошайка",
    r"еблан",
    r"хохлы"
]

PROHIBITED_WORDS = [
    "путин", "зеленский", "хохол", "зетники",
    "гондоны", "политика", "пендос", "омерика", "америка"
]

MUT_WORDS_RE = re.compile(r"\b(подайте|дайте|дай)\b", re.IGNORECASE)
URL_RE = re.compile(r"(https?://(?!((www\.)?(youtube\.com|youtu\.be|vk\.com|m\.vk\.com)))[\w.-]+\.\S+)", re.IGNORECASE)

RACIAL_SLURS_RE = re.compile("|".join(RACIAL_SLURS), re.IGNORECASE)
PROHIBITED_WORDS_RE = re.compile("|".join(PROHIBITED_WORDS), re.IGNORECASE)

@dp.message()
async def handle_message(message: Message):
    if not message.text or message.chat.type not in ['group', 'supergroup'] or message.from_user.is_bot:
        return

    user = message.from_user
    text = message.text
    text_lower = text.lower()

    # Команда "правила"
    if text_lower == "правила":
        await message.reply(
            "🗓 <b>Правила чата:</b>\n\n"
            "🛑 Вы можете получить бан / мут за следующие действия:\n\n"
            "1. Массовая рассылка сообщений или флуд без разрешения администрации.\n"
            "2. Попрошайничество.\n"
            "3. Оскорбление участников.\n"
            "4. Злоупотребление заглавными буквами.\n"
            "5. Отправка скримеров, стонов или распространение непристойного контента.\n"
            "6. Торговля без согласия администрации.\n"
            "7. Реклама в любом виде.\n"
            "8. Оскорбления в адрес администрации.\n"
            "9. Провокация конфликтов.\n"
            "10. Попытка раскрыть личные данные администрации.\n"
            "11. Обвинения в мошенничестве без доказательств.\n"
            "12. Оскорбления в адрес родственников участников.\n"
            "13. Жалобы на контент постов.\n"
            "14. Создание конфликтных ситуаций.\n"
            "15. Мошенничество или участие в схемах обмана.\n"
            "16. Обсуждение политических тем.\n"
            "17. Жестокий или шокирующий контент.\n"
            "18. Призывы выступать против автора.\n"
            "19. Ненужный флуд и бессмысленное общение.\n"
            "20. Шутки на тему мошенничества.\n"
            "21. Оскорбление религиозных чувств и вероисповеданий.\n"
            "22. Размещение личной информации других пользователей без их согласия.\n"
            "23. Распространение ложной или вводящей в заблуждение информации.\n"
            "24. Создание множества учетных записей для обхода блокировок.\n"
            "25. Публикация или обмен вредоносными файлами.\n\n"
            "👑 <b>Главный администратор</b> — <a href=\"https://t.me/IUVB76I\">@IUVB76I</a>\n\n"
            "⚠️ Администрация оставляет за собой право принимать решения о блокировке на разный срок. "
            "Меры наказания могут варьироваться, и возможна устная просьба о корректировке поведения в первый раз.",
            parse_mode=ParseMode.HTML
        )
        return

    # Спам-фильтр
    now = datetime.now()
    if user.id not in USER_MESSAGE_HISTORY:
        USER_MESSAGE_HISTORY[user.id] = []
    USER_MESSAGE_HISTORY[user.id] = [m for m in USER_MESSAGE_HISTORY[user.id] if (now - m["time"]).total_seconds() <= SPAM_TIME_SECONDS]
    USER_MESSAGE_HISTORY[user.id].append({"text": text_lower, "time": now})
    if len([m for m in USER_MESSAGE_HISTORY[user.id] if m["text"] == text_lower]) >= SPAM_LIMIT:
        if await can_restrict_member(message.chat.id, user.id):
            await mute_user(message.chat.id, user.id, timedelta(minutes=5), "Спам", user.full_name)
            await message.delete()
        return

    # Проверка на мат, политику, попрошайничество, ссылки
    if RACIAL_SLURS_RE.search(text_lower) or PROHIBITED_WORDS_RE.search(text_lower):
        if await can_restrict_member(message.chat.id, user.id):
            await mute_user(message.chat.id, user.id, timedelta(minutes=10), "Запрещённые слова", user.full_name)
            await message.delete()
        return

    if MUT_WORDS_RE.search(text_lower):
        if await can_restrict_member(message.chat.id, user.id):
            await mute_user(message.chat.id, user.id, timedelta(minutes=10), "Попрошайничество", user.full_name)
            await message.delete()
        return

    if URL_RE.search(text_lower):
        # Допустим ссылки разрешены только на YouTube и VK, остальные удаляем и мутим
        if await can_restrict_member(message.chat.id, user.id):
            await mute_user(message.chat.id, user.id, timedelta(minutes=10), "Запрещённая ссылка", user.full_name)
            await message.delete()
        return

    # Обработка команды "мут"
    if text_lower.startswith('мут'):
        if not message.reply_to_message:
            await message.reply("⚠️ Для команды мут нужно ответить на сообщение пользователя.")
            return

        args = text_lower.split()
        if len(args) < 3:
            await message.reply("⚠️ Формат команды: мут <число> <единица времени> <причина>")
            return

        duration_text = ' '.join(args[1:3])  # Например, '1 час'
        reason = ' '.join(args[3:]) if len(args) > 3 else "Без причины"

        duration = parse_duration(duration_text)
        if duration is None:
            await message.reply("⚠️ Неверный формат времени. Используйте, например: 10 минут, 1 час, 2 дня")
            return

        target_user = message.reply_to_message.from_user
        if not await can_restrict_member(message.chat.id, target_user.id):
            await message.reply("⚠️ Не могу замутить данного пользователя.")
            return

        await mute_user(message.chat.id, target_user.id, duration, reason, target_user.full_name)
        return

    # Обработка команды "размут"
    if text_lower.startswith('размут'):
        if not message.reply_to_message:
            await message.reply("⚠️ Для команды размут нужно ответить на сообщение пользователя.")
            return

        target_user = message.reply_to_message.from_user
        if not await can_restrict_member(message.chat.id, target_user.id):
            await message.reply("⚠️ Не могу размутить данного пользователя.")
            return

        await unmute_user(message.chat.id, target_user.id, target_user.full_name)
        return

    # Обработка команды "варн"
    if text_lower.startswith('варн'):
        if not message.reply_to_message:
            await message.reply("⚠️ Для команды варн нужно ответить на сообщение пользователя.")
            return

        reason = text.partition(' ')[2].partition(' ')[2]
        if not reason:
            reason = "Без причины"

        target_user = message.reply_to_message.from_user
        await warn_user(message.chat.id, target_user.id, target_user.full_name, reason, message)
        return

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if not message.reply_to_message:
        await message.reply("⚠️ Для команды /ban нужно ответить на сообщение пользователя.")
        return
    
    target_user = message.reply_to_message.from_user
    if not await can_restrict_member(message.chat.id, target_user.id):
        await message.reply("⚠️ Не могу забанить данного пользователя.")
        return
    
    try:
        await bot.ban_chat_member(message.chat.id, target_user.id)
        await message.reply(f"⛔ Пользователь {build_user_link(target_user.full_name, target_user.id)} забанен.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.reply(f"Ошибка при бане: {e}")

@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    if not message.reply_to_message:
        await message.reply("⚠️ Для команды /unban нужно ответить на сообщение пользователя.")
        return
    
    target_user = message.reply_to_message.from_user
    
    try:
        await bot.unban_chat_member(message.chat.id, target_user.id)
        await message.reply(f"✅ Пользователь {build_user_link(target_user.full_name, target_user.id)} разбанен.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.reply(f"Ошибка при разбане: {e}")

@dp.message(Command("bot"))
async def cmd_bot(message: Message):
    await message.reply("🤖 Я — модератор-бот, помогаю поддерживать порядок в чате.")
if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))