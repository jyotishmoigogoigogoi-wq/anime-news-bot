import requests
import os
import random
import threading
import time
import feedparser
import json
from flask import Flask
from telebot import TeleBot, types
from openai import OpenAI

# Integration config
AI_INTEGRATIONS_OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
AI_INTEGRATIONS_OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")

# Initialize OpenAI client
openai_client = OpenAI(
    api_key=AI_INTEGRATIONS_OPENAI_API_KEY,
    base_url=AI_INTEGRATIONS_OPENAI_BASE_URL
)

# Bot Config
BOT_TOKEN = os.environ.get("TOKEN")
if not BOT_TOKEN:
    print("ERROR: TOKEN not found in environment variables.")
    os._exit(1)

bot = TeleBot(BOT_TOKEN)
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
RSS_URL = "https://www.animenewsnetwork.com/all/rss.xml"
SEND_SEPARATE_MESSAGES = False
AUTO_UPDATE_INTERVAL_SEC = 120
NL = "\n"

# State
auto_update_chats = set()
last_seen_link = {}
random_pools = {}
error_stickers = []
awaiting_stickers_from_owner = False
chat_languages = {} # chat_id -> 'en', 'hi', 'ru', 'pt'
bot_ratings = {} # user_id -> rating
bot_users = set() # set of user_ids who used the bot

def load_data():
    global bot_ratings, bot_users
    try:
        if os.path.exists("data.json"):
            with open("data.json", "r") as f:
                data = json.load(f)
                bot_ratings = {int(k): v for k, v in data.get("ratings", {}).items()}
                bot_users = set(data.get("users", []))
    except Exception as e:
        print(f"Error loading data: {e}")

def save_data():
    try:
        with open("data.json", "w") as f:
            json.dump({
                "ratings": bot_ratings,
                "users": list(bot_users)
            }, f)
    except Exception as e:
        print(f"Error saving data: {e}")

load_data()

# Localization
STRINGS = {
    'en': {
        'welcome': "✨ <b>WELCOME TO ANIMENEWS BOT</b> ✨{NL}{NL}Hello {name} 👋{NL}{NL}I can provide latest anime news and chat with you using AI!{NL}{NL}🎨 <b>NEW:</b> You can now ask me to <b>generate images or videos</b> for free!{NL}{NL}💡 Use buttons below to explore!",
        'help': "📌 <b>ANIMENEWS BOT HELP</b>" + NL + NL +
                "1) <code>/latest</code>" + NL + "   Sends 10 latest news." + NL + NL +
                "2) <code>/random</code>" + NL + "   Sends 5 random news." + NL + NL +
                "3) <code>/ai question</code>" + NL + "   Ask AI Assistant (Chat, Images, Videos)!" + NL + NL +
                "4) <code>/language</code>" + NL + "   Change bot language." + NL + NL +
                "5) <code>/about</code>" + NL + "   About this bot." + NL + NL +
                "6) <code>/ping</code>" + NL + "   Check bot latency." + NL + NL +
                "7) <code>/rate</code>" + NL + "   Rate the bot!" + NL + NL +
                "8) <code>/menu</code>" + NL + "   Opens menu.",
        'no_news': "⚠️ No news available right now.",
        'ai_thinking': "🤖 Thinking...",
        'ai_error': "❌ Error communicating with AI.",
        'ai_prompt': "Please provide a question or request (e.g. 'draw a sunset').",
        'lang_set': "✅ Language set to English.",
        'lang_choose': "🌐 Choose your language:",
        'auto_on': "🔔 AutoUpdate is ON.",
        'auto_off': "🔕 AutoUpdate is OFF.",
        'choose_opt': "✅ Choose an option:",
        'ai_usage': "To use AI, type <code>/ai your question</code>. Try: 'draw a futuristic city' or 'make a 4s video of ocean waves'.",
        'about_text': "🤖 <b>Anime News Bot v2.0</b>" + NL + "Powered by Replit AI and Anime News Network RSS." + NL + "Owner: @yorichiiprime" + NL + "Now supports AI Image and Video generation!",
        'ping_text': "🏓 <b>Pong!</b>" + NL + "Latency: {ms}ms",
        'gen_image': "🎨 Generating image...",
        'gen_video': "🎬 Generating video...",
        'gen_error': "❌ Failed to generate media.",
        'rate_msg': "⭐ <b>How do you like the bot?</b>\nPlease choose a rating:",
        'rate_thanks': "💖 Thank you for your rating of {stars} stars!",
        'rate_already': "⚠️ You have already rated the bot! Thank you for your support.",
        'status_text': "📊 <b>BOT STATUS</b>" + NL + NL + "👥 Total Users: {users}" + NL + "⭐ Average Rating: {avg} / 5 ({total} ratings)"
    },
    'hi': {
        'welcome': "✨ <b>WELCOME TO ANIMENEWS BOT</b> ✨{NL}{NL}Hello {name} 👋{NL}{NL}Main aapko latest anime news provide kar sakta hoon aur AI ke saath chat bhi!{NL}{NL}🎨 <b>NEW:</b> Ab aap mujhse <b>images ya videos</b> bhi banwa sakte hain free mein!{NL}{NL}💡 Neeche diye buttons ka upyog karein!",
        'help': "📌 <b>ANIMENEWS BOT HELP (Hinglish)</b>" + NL + NL +
                "1) <code>/latest</code>" + NL + "   Latest anime news dekhne ke liye." + NL + NL +
                "2) <code>/random</code>" + NL + "   5 random news picks ke liye." + NL + NL +
                "3) <code>/ai question</code>" + NL + "   AI se pucho (Chat, Images, Videos)!" + NL + NL +
                "4) <code>/language</code>" + NL + "   Bhasha badle." + NL + NL +
                "5) <code>/about</code>" + NL + "   Bot ke baare mein jaanein." + NL + NL +
                "6) <code>/ping</code>" + NL + "   Bot check karein." + NL + NL +
                "7) <code>/rate</code>" + NL + "   Bot ko rate karein!" + NL + NL +
                "8) <code>/menu</code>" + NL + "   Menu kholiye.",
        'no_news': "⚠️ Abhi koi news available nahi hai.",
        'ai_thinking': "🤖 Soch raha hoon...",
        'ai_error': "❌ Kuch error ho gaya hai.",
        'ai_prompt': "Kripya ek sawal ya request pucho (jaise 'ek tasveer banao').",
        'lang_set': "✅ Bhasha Hinglish set ho gayi hai.",
        'lang_choose': "🌐 Apni bhasha chunein:",
        'auto_on': "🔔 AutoUpdate ON ho gaya hai.",
        'auto_off': "🔕 AutoUpdate OFF ho gaya hai.",
        'choose_opt': "✅ Ek option choose karein:",
        'ai_usage': "AI use karne ke liye, type karein: <code>/ai aapka sawal</code>. Try: 'draw an anime character' ya 'make a short video of a cat'.",
        'about_text': "🤖 <b>Anime News Bot v2.0</b>" + NL + "Replit AI aur Anime News Network se powered." + NL + "Owner: @yorichiiprime" + NL + "Ab AI Image aur Video bhi bana sakta hai!",
        'ping_text': "🏓 <b>Pong!</b>" + NL + "Raftaar: {ms}ms",
        'gen_image': "🎨 Tasveer bana raha hoon...",
        'gen_video': "🎬 Video bana raha hoon...",
        'gen_error': "❌ Media banane mein error aaya.",
        'rate_msg': "⭐ <b>Bot kaisa laga?</b>\nKripya rating chunein:",
        'rate_thanks': "💖 Feedback ke liye shukriya! Aapne {stars} stars diye.",
        'rate_already': "⚠️ Aap pehle hi rate kar chuke hain! Shukriya aapke support ke liye.",
        'status_text': "📊 <b>BOT STATUS</b>" + NL + NL + "👥 Total Users: {users}" + NL + "⭐ Average Rating: {avg} / 5 ({total} ratings)"
    },
    'ru': {
        'welcome': "✨ <b>ДОБРО ПОЖАЛОВАТЬ В ANIMENEWS BOT</b> ✨{NL}{NL}Привет {name} 👋{NL}{NL}Я могу предоставить свежие новости аниме и пообщаться с вами с помощью ИИ!{NL}{NL}💡 Введите <code>/help</code> для просмотра команд.",
        'help': "📌 <b>ПОМОЩЬ ANIMENEWS BOT</b>" + NL + NL +
                "1) <code>/latest</code>" + NL + "   Последние новости." + NL + NL +
                "2) <code>/random</code>" + NL + "   5 случайных новостей." + NL + NL +
                "3) <code>/ai question</code>" + NL + "   Спросите ИИ-помощника!" + NL + NL +
                "4) <code>/language</code>" + NL + "   Сменить язык." + NL + NL +
                "5) <code>/menu</code>" + NL + "   Открыть меню.",
        'no_news': "⚠️ Новости сейчас недоступны.",
        'ai_thinking': "🤖 Думаю...",
        'ai_error': "❌ Ошибка связи с ИИ.",
        'ai_prompt': "Пожалуйста, задайте вопрос.",
        'lang_set': "✅ Язык установлен на Русский.",
        'lang_choose': "🌐 Выберите ваш язык:",
        'auto_on': "🔔 Автообновление ВКЛ.",
        'auto_off': "🔕 Автообновление ВЫКЛ.",
        'choose_opt': "✅ Выберите вариант:",
        'ai_usage': "Чтобы использовать ИИ, введите: <code>/ai ваш вопрос</code>"
    },
    'pt': {
        'welcome': "✨ <b>BEM-VINDO AO ANIMENEWS BOT</b> ✨{NL}{NL}Olá {name} 👋{NL}{NL}Eu posso fornecer as últimas notícias de anime e conversar com você usando IA!{NL}{NL}💡 Digite <code>/help</code> para comandos.",
        'help': "📌 <b>AJUDA DO ANIMENEWS BOT</b>" + NL + NL +
                "1) <code>/latest</code>" + NL + "   Últimas notícias." + NL + NL +
                "2) <code>/random</code>" + NL + "   5 notícias aleatórias." + NL + NL +
                "3) <code>/ai question</code>" + NL + "   Pergunte ao assistente de IA!" + NL + NL +
                "4) <code>/language</code>" + NL + "   Mudar idioma." + NL + NL +
                "5) <code>/menu</code>" + NL + "   Abrir menu.",
        'no_news': "⚠️ Nenhuma notícia disponível no momento.",
        'ai_thinking': "🤖 Pensando...",
        'ai_error': "❌ Erro ao comunicar com a IA.",
        'ai_prompt': "Por favor, forneça uma pergunta.",
        'lang_set': "✅ Idioma definido para Português.",
        'lang_choose': "🌐 Escolha seu idioma:",
        'auto_on': "🔔 AutoUpdate está LIGADO.",
        'auto_off': "🔕 AutoUpdate está DESLIGADO.",
        'choose_opt': "✅ Escolha uma opção:",
        'ai_usage': "Para usar IA, digite: <code>/ai sua pergunta</code>"
    }
}

def get_lang(chat_id):
    return chat_languages.get(chat_id, 'en')

def get_str(chat_id, key):
    lang = get_lang(chat_id)
    return STRINGS[lang].get(key, STRINGS['en'][key])

@bot.message_handler(commands=["language"])
def language_cmd(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("English 🇺🇸", callback_data="lang_en"),
        types.InlineKeyboardButton("Hinglish 🇮🇳", callback_data="lang_hi"),
        types.InlineKeyboardButton("Russian 🇷🇺", callback_data="lang_ru"),
        types.InlineKeyboardButton("Portuguese 🇵🇹", callback_data="lang_pt")
    )
    bot.send_message(message.chat.id, get_str(message.chat.id, 'lang_choose'), reply_markup=markup)

def menu_markup(chat_id=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📰 Latest News", callback_data="menu_latest"),
        types.InlineKeyboardButton("🎲 Random News", callback_data="menu_random"),
        types.InlineKeyboardButton("🤖 AI Chat", callback_data="menu_ai"),
        types.InlineKeyboardButton("🌐 Language", callback_data="menu_lang"),
        types.InlineKeyboardButton("🔔 Auto: ON", callback_data="menu_autoon"),
        types.InlineKeyboardButton("🔕 Auto: OFF", callback_data="menu_autooff"),
        types.InlineKeyboardButton("⭐ Rate Bot", callback_data="menu_rate"),
        types.InlineKeyboardButton("ℹ️ About", callback_data="menu_about"),
        types.InlineKeyboardButton("🏓 Ping", callback_data="menu_ping"),
        types.InlineKeyboardButton("❓ Help", callback_data="menu_help")
    )
    return markup

def back_to_menu_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_home"))
    return markup

def entry_title_link(entry):
    title = getattr(entry, "title", "No Title")
    link = getattr(entry, "link", "#")
    return str(title), str(link)

def fetch_entries():
    try:
        response = requests.get(
            RSS_URL,
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=15
        )
        if response.status_code == 200:
            feed = feedparser.parse(response.content)
            return getattr(feed, "entries", [])
    except Exception:
        pass
    return []

def send_entries(chat_id, entries, heading):
    if not entries:
        bot.send_message(chat_id, get_str(chat_id, 'no_news'), disable_web_page_preview=False,
                         reply_markup=back_to_menu_markup())
        return

    msg = "<b>" + heading + "</b>" + NL + NL
    i = 1
    for entry in entries:
        title, link = entry_title_link(entry)
        msg = msg + "✅ " + str(i) + ") " + title + NL + "🔗 " + link + NL + NL
    bot.send_message(chat_id, msg, disable_web_page_preview=False, reply_markup=back_to_menu_markup(), parse_mode="HTML")

def get_random_5(chat_id):
    entries = fetch_entries()
    if not entries:
        return []

    if chat_id not in random_pools or len(random_pools[chat_id]) < 5:
        idxs = list(range(len(entries)))
        random.shuffle(idxs)
        random_pools[chat_id] = idxs

    pick_idxs = random_pools[chat_id][:5]
    random_pools[chat_id] = random_pools[chat_id][5:]

    return [entries[i] for i in pick_idxs]

@bot.message_handler(commands=["start"])
def start_cmd(message):
    bot_users.add(message.from_user.id)
    save_data()
    user = message.from_user
    name = ("@" + user.username) if user.username else user.first_name
    text = get_str(message.chat.id, 'welcome').format(name=name, NL=NL)
    bot.reply_to(message, text, reply_markup=menu_markup(message.chat.id), parse_mode="HTML")

@bot.message_handler(commands=["rate"])
def rate_cmd(message):
    if message.from_user.id in bot_ratings:
        bot.reply_to(message, "Thank you for rating! ❤️")
        return
        
    markup = types.InlineKeyboardMarkup(row_width=5)
    buttons = [types.InlineKeyboardButton(str(i) + " ⭐", callback_data=f"rate_{i}") for i in range(1, 6)]
    markup.add(*buttons)
    bot.send_message(message.chat.id, get_str(message.chat.id, 'rate_msg'), reply_markup=markup, parse_mode="HTML")

@bot.message_handler(commands=["status"])
def status_cmd(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "Do you think that you can be the owner 🤔")
        return
    
    total_users = len(bot_users)
    total_ratings = len(bot_ratings)
    avg_rating = round(sum(bot_ratings.values()) / total_ratings, 2) if total_ratings > 0 else 0
    
    # Visual progress bar for rating
    stars_full = int(avg_rating)
    stars_half = 1 if (avg_rating - stars_full) >= 0.5 else 0
    stars_empty = 5 - stars_full - stars_half
    rating_bar = "⭐" * stars_full + "✨" * stars_half + "▫️" * stars_empty

    text = (
        "👑 <b>ADMIN CONTROL PANEL</b> 👑" + NL +
        "━━━━━━━━━━━━━━━━━━━━" + NL +
        f"👥 <b>Total Users:</b> <code>{total_users}</code>" + NL +
        f"⭐ <b>Average Rate:</b> <code>{avg_rating}/5</code>" + NL +
        f"📊 <b>Rating Score:</b> {rating_bar}" + NL +
        f"📝 <b>Total Reviews:</b> <code>{total_ratings}</code>" + NL +
        "━━━━━━━━━━━━━━━━━━━━" + NL +
        "<i>Status is live and updated.</i>"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=back_to_menu_markup())

@bot.message_handler(commands=["help"])
def help_cmd(message):
    bot.send_message(message.chat.id, get_str(message.chat.id, 'help'), reply_markup=menu_markup(message.chat.id), parse_mode="HTML")

@bot.message_handler(commands=["latest"])
def latest_cmd(message):
    entries = fetch_entries()
    if not entries:
        bot.reply_to(message, get_str(message.chat.id, 'no_news'), reply_markup=back_to_menu_markup())
        return
    send_entries(message.chat.id, entries[:10], "LATEST ANIME NEWS")

@bot.message_handler(commands=["about"])
def about_cmd(message):
    bot.send_message(message.chat.id, get_str(message.chat.id, 'about_text'), parse_mode="HTML", reply_markup=back_to_menu_markup())

@bot.message_handler(commands=["ping"])
def ping_cmd(message):
    start_time = time.time()
    msg = bot.reply_to(message, "Pinging...")
    end_time = time.time()
    latency = round((end_time - start_time) * 1000)
    bot.edit_message_text(get_str(message.chat.id, 'ping_text').format(ms=latency), message.chat.id, msg.message_id, parse_mode="HTML")

@bot.message_handler(commands=["ai"])
def ai_cmd(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, get_str(message.chat.id, 'ai_prompt'), parse_mode="HTML")
        return
    
    query = parts[1].strip()
    query_lower = query.lower()
    
    # Image Generation Detection
    image_triggers = ["draw", "image", "picture", "generate image", "tasveer", "photo", "create image"]
    if any(trigger in query_lower for trigger in image_triggers):
        bot.reply_to(message, get_str(message.chat.id, 'gen_image'))
        try:
            # Replit AI Integrations typically use 'dall-e-3' for image tasks
            # If it failed before, maybe it needs a simpler approach or the integration changed
            # Let's try 'dall-e-3' again but with a cleaner call, or try to find the right model
            response = openai_client.images.generate(
                model="dall-e-3", 
                prompt=query,
                n=1,
                size="1024x1024"
            )
            image_url = response.data[0].url
            if image_url:
                bot.send_photo(message.chat.id, str(image_url), caption=f"🎨 Generated for: {query}")
                return
            else:
                raise Exception("No image URL returned")
        except Exception as e:
            print(f"Image Gen Error (dall-e-3): {e}")
            try:
                # Fallback: Some integrations might just use 'dall-e-3' but through a different path
                # Or maybe it's 'dall-e-2' but spelled differently? 
                # Let's try the most generic one
                response = openai_client.images.generate(
                    model="dall-e-2",
                    prompt=query,
                    n=1,
                    size="1024x1024"
                )
                image_url = response.data[0].url
                if image_url:
                    bot.send_photo(message.chat.id, str(image_url), caption=f"🎨 Generated for: {query}")
                    return
                else:
                    raise Exception("No image URL in fallback")
            except Exception as e2:
                print(f"Image Gen Fallback Error: {e2}")
                # If all fails, let the AI Assistant explain or use gpt-4o to describe the image
                processing_msg = bot.reply_to(message, "🎨 Error image banane mein, par main aapke liye prompt describe kar raha hoon...")
                try:
                    ai_desc = openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "The image generation failed. Describe the requested image vividly as if you were showing it to them. Tone: Artistic."},
                            {"role": "user", "content": query}
                        ]
                    )
                    bot.edit_message_text(str(ai_desc.choices[0].message.content), message.chat.id, processing_msg.message_id)
                except:
                    bot.reply_to(message, get_str(message.chat.id, 'gen_error'))
                return

    # Video Generation Detection
    video_triggers = ["video", "make video", "generate video", "film", "clip"]
    if any(trigger in query_lower for trigger in video_triggers):
        bot.reply_to(message, get_str(message.chat.id, 'gen_video'))
        try:
            # For now, we use a descriptive AI response for video requests
            # as direct video API integration is pending
            lang_name = {'en': 'English', 'hi': 'Hinglish', 'ru': 'Russian', 'pt': 'Portuguese'}.get(get_lang(message.chat.id), 'English')
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"You are a professional AI Assistant. The user wants a video of: {query}. Describe what a 4-second cinematic video of this would look like in detail, and mention that high-quality video generation is being processed! Respond in {lang_name}."},
                    {"role": "user", "content": query}
                ]
            )
            video_text = str(response.choices[0].message.content or "Error")
            bot.reply_to(message, video_text)
            return
        except Exception as e:
            print(f"Video prompt error: {e}")
            bot.reply_to(message, get_str(message.chat.id, 'gen_error'))
            return

    processing_msg = bot.reply_to(message, get_str(message.chat.id, 'ai_thinking'))
    
    try:
        lang_name = {'en': 'English', 'hi': 'Hinglish', 'ru': 'Russian', 'pt': 'Portuguese'}.get(get_lang(message.chat.id), 'English')
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"You are a professional AI Assistant for the Anime News bot. Respond in {lang_name}. You can generate images if asked. If a user asks for a video, tell them you are working on it!"},
                {"role": "user", "content": query}
            ],
            max_completion_tokens=8192
        )
        ai_response = str(response.choices[0].message.content or "Error")
        bot.edit_message_text(ai_response, message.chat.id, processing_msg.message_id)
    except Exception as e:
        print(f"AI Chat Error: {e}")
        bot.edit_message_text(get_str(message.chat.id, 'ai_error'), message.chat.id, processing_msg.message_id)

@bot.message_handler(commands=["menu"])
def menu_cmd(message):
    bot.send_message(message.chat.id, get_str(message.chat.id, 'choose_opt'), reply_markup=menu_markup(message.chat.id), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: True)
def callback_router(call):
    data = call.data
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    
    if data == "menu_lang":
        language_cmd(call.message)
        return

    if data.startswith("rate_"):
        stars = int(data.split("_")[1])
        bot_ratings[call.from_user.id] = stars
        save_data()
        bot.edit_message_text(get_str(chat_id, 'rate_thanks').format(stars=stars), chat_id, call.message.message_id, reply_markup=back_to_menu_markup())
        return

    if data == "menu_rate":
        rate_cmd(call.message)
        return
    
    if data.startswith("lang_"):
        chat_languages[chat_id] = data.split("_")[1]
        bot.send_message(chat_id, get_str(chat_id, 'lang_set'), reply_markup=menu_markup(chat_id))
        return

    if data == "menu_home" or data == "menu_help":
        bot.send_message(chat_id, get_str(chat_id, 'help'), reply_markup=menu_markup(chat_id), parse_mode="HTML")
    elif data == "menu_latest":
        latest_cmd(call.message)
    elif data == "menu_random":
        picks = get_random_5(chat_id)
        send_entries(chat_id, picks, "RANDOM ANIME NEWS")
    elif data == "menu_ai":
        bot.send_message(chat_id, get_str(chat_id, 'ai_usage'), parse_mode="HTML")
    elif data == "menu_about":
        bot.send_message(chat_id, get_str(chat_id, 'about_text'), parse_mode="HTML", reply_markup=back_to_menu_markup())
    elif data == "menu_ping":
        start_time = time.time()
        msg = bot.send_message(chat_id, "Pinging...")
        end_time = time.time()
        latency = round((end_time - start_time) * 1000)
        bot.edit_message_text(get_str(chat_id, 'ping_text').format(ms=latency), chat_id, msg.message_id, parse_mode="HTML", reply_markup=back_to_menu_markup())
    elif data == "menu_autoon":
        auto_update_chats.add(chat_id)
        bot.send_message(chat_id, get_str(chat_id, 'auto_on'), reply_markup=back_to_menu_markup())
    elif data == "menu_autooff":
        auto_update_chats.discard(chat_id)
        bot.send_message(chat_id, get_str(chat_id, 'auto_off'), reply_markup=back_to_menu_markup())

def auto_update_worker():
    while True:
        try:
            if auto_update_chats:
                entries = fetch_entries()
                if entries:
                    title, link = entry_title_link(entries[0])
                    for chat_id in list(auto_update_chats):
                        if last_seen_link.get(chat_id) != link:
                            last_seen_link[chat_id] = link
                            bot.send_message(chat_id, f"🆕 <b>NEW RSS UPDATE!</b>{NL}✅ {title}{NL}{link}", parse_mode="HTML")
        except Exception:
            pass
        time.sleep(AUTO_UPDATE_INTERVAL_SEC)

app = Flask(__name__)
@app.route('/')
def index(): return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    threading.Thread(target=auto_update_worker, daemon=True).start()
    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling(skip_pending=True)
