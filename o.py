import os
import asyncio
import random
import threading
import json
from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, UserAlreadyParticipantError
from telethon.tl.functions.messages import ImportChatInviteRequest, SendReactionRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.types import ReactionEmoji, DataJSON
import telebot

# Firebase Optional Integration (agar Firebase credentials hain toh Firestore use hoga, warna local JSON fallback)
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

# Credentials Environment Variables
API_ID = int(os.environ.get("API_ID", 39657203))
API_HASH = os.environ.get("API_HASH", "23e8ed432a027ca9bee88c452098a188")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8648126819:AAGLK2azI6lIy-kCwsKE9r0FCo4KIWBzXC8")
ADMIN_BOT_TOKEN = os.environ.get("ADMIN_BOT_TOKEN", "8844345688:AAF-7TCs8GO2Ki9DRx3GaQCQgYti6zwEhYY")
OWNER_ID = int(os.environ.get("OWNER_ID", 7864770297))

bot = telebot.TeleBot(BOT_TOKEN)
admin_bot = telebot.TeleBot(ADMIN_BOT_TOKEN)

DB_FILE = "database.json"

# Database Initialization (Firebase Firestore or Local JSON fallback)
db = None
if FIREBASE_AVAILABLE and os.environ.get("FIREBASE_CREDENTIALS"):
    try:
        cred_path = os.environ.get("FIREBASE_CREDENTIALS")
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("[INFO] Connected to Firebase Firestore successfully!")
    except Exception as e:
        print(f"[WARNING] Firebase init failed: {e}. Falling back to local JSON DB.")

def load_db():
    if db:
        try:
            sessions_ref = db.collection("bot_data").document("sessions").get()
            sessions = sessions_ref.to_dict().get("data", {}) if sessions_ref.exists else {}
            admins_ref = db.collection("bot_data").document("admins").get()
            stored_admins = admins_ref.to_dict().get("data", [OWNER_ID]) if admins_ref.exists else [OWNER_ID]
            return sessions, set(stored_admins)
        except Exception as e:
            print(f"[DB ERROR] {e}")
    
    # Local JSON Fallback
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f)
                return data.get("sessions", {}), set(data.get("admins", [OWNER_ID]))
        except:
            pass
    return {}, {OWNER_ID}

def save_sessions_db(sessions_dict):
    if db:
        try:
            db.collection("bot_data").document("sessions").set({"data": sessions_dict})
            return
        except Exception as e:
            print(f"[DB ERROR] {e}")
            
    # Local JSON Fallback
    data = {"sessions": sessions_dict, "admins": list(admins)}
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_admins_db(admins_set):
    if db:
        try:
            db.collection("bot_data").document("admins").set({"data": list(admins_set)})
            return
        except Exception as e:
            print(f"[DB ERROR] {e}")

    sessions, _ = load_db()
    data = {"sessions": sessions, "admins": list(admins_set)}
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Load Initial Data
saved_sessions, admins = load_db()
user_temp_data = {}
active_services = {}  # { link: { "count": X, "stop_event": event, "sessions": [...] } }


@admin_bot.message_handler(commands=["start"])
def admin_start(message):
    if message.from_user.id != OWNER_ID:
        admin_bot.send_message(message.chat.id, "❌ Aap is Admin Bot ke Owner nahi hain!")
        return

    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton("➕ Admin Banayein", callback_data="add_admin"),
        telebot.types.InlineKeyboardButton("➖ Admin Hataein", callback_data="remove_admin"),
        telebot.types.InlineKeyboardButton("📋 All Admins Dekhein", callback_data="list_admins"),
    )
    admin_bot.send_message(
        message.chat.id,
        "⚙️ **Admin Control Panel**\n\nKripya option select karein:",
        reply_markup=markup,
        parse_mode="Markdown",
    )


@admin_bot.callback_query_handler(func=lambda call: True)
def admin_callback(call):
    if call.from_user.id != OWNER_ID:
        admin_bot.answer_callback_query(call.id, "❌ Access Denied!", show_alert=True)
        return

    chat_id = call.message.chat.id

    if call.data == "add_admin":
        msg = admin_bot.send_message(chat_id, "👤 Jise admin banana hai, uski **Telegram User ID** bhejein:")
        admin_bot.register_next_step_handler(msg, process_add_admin)

    elif call.data == "remove_admin":
        msg = admin_bot.send_message(chat_id, "👤 Jise admin list se hatana hai, uski **Telegram User ID** bhejein:")
        admin_bot.register_next_step_handler(msg, process_remove_admin)

    elif call.data == "list_admins":
        text = "📋 **Current Admins List:**\n\n"
        for uid in admins:
            role = "👑 (Owner)" if uid == OWNER_ID else "⚡ (Admin)"
            text += f"• `{uid}` {role}\n"
        admin_bot.send_message(chat_id, text, parse_mode="Markdown")


def process_add_admin(message):
    try:
        new_id = int(message.text.strip())
        admins.add(new_id)
        save_admins_db(admins)
        admin_bot.send_message(message.chat.id, f"✅ User ID `{new_id}` ko successfully **Admin** bana diya gaya hai!", parse_mode="Markdown")
    except ValueError:
        admin_bot.send_message(message.chat.id, "❌ Galat User ID! Kripya sirf numbers bhejein.")


def process_remove_admin(message):
    try:
        rem_id = int(message.text.strip())
        if rem_id == OWNER_ID:
            admin_bot.send_message(message.chat.id, "❌ Aap Owner ID ko remove nahi kar sakte!")
            return
        if rem_id in admins:
            admins.remove(rem_id)
            save_admins_db(admins)
            admin_bot.send_message(message.chat.id, f"🗑️ User ID `{rem_id}` ko Admin list se hata diya gaya hai!", parse_mode="Markdown")
        else:
            admin_bot.send_message(message.chat.id, "⚠️ Yeh ID Admin list me nahi hai.")
    except ValueError:
        admin_bot.send_message(message.chat.id, "❌ Galat User ID! Kripya sirf numbers bhejein.")


def is_authorized_user(user_id):
    return user_id in admins


@bot.message_handler(commands=["start"])
def send_welcome(message):
    if not is_authorized_user(message.from_user.id):
        return

    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton("➕ ID Add Karein (Login)", callback_data="add_id"),
        telebot.types.InlineKeyboardButton("📋 Meri IDs Dekhein (Numbered)", callback_data="list_ids"),
        telebot.types.InlineKeyboardButton("✏️ ID ka Naam Change Karein", callback_data="change_name"),
        telebot.types.InlineKeyboardButton("📢 Channel/Group me Members Dalein", callback_data="add_members"),
        telebot.types.InlineKeyboardButton("🚀 Multi-Channel 24/7 Anti-Drop VC", callback_data="start_service"),
        telebot.types.InlineKeyboardButton("📊 Active Services Dekhein", callback_data="view_services"),
        telebot.types.InlineKeyboardButton("🛑 Service Off (Stop)", callback_data="stop_service"),
    )
    bot.send_message(
        message.chat.id,
        "👋 **Telegram 24/7 Advanced Manager Bot**\n\nOption select karein:",
        reply_markup=markup,
        parse_mode="Markdown",
    )


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if not is_authorized_user(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Aapko is bot ke access ka permission nahi hai!", show_alert=True)
        return

    chat_id = call.message.chat.id

    if call.data == "add_id":
        msg = bot.send_message(chat_id, "📱 Apna phone number country code ke sath bhejein (Jaise: `+919876543210`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_phone_number)

    elif call.data == "list_ids":
        show_ids_list(chat_id)

    elif call.data == "change_name":
        msg = bot.send_message(chat_id, "📱 Jis ID ka naam change karna hai uska phone number bhejein (Jaise: `+919876543210`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_name_phone)

    elif call.data == "add_members":
        msg = bot.send_message(chat_id, "🔗 Jis Channel ya Group me members add karne hain, uska link ya username bhejein:")
        bot.register_next_step_handler(msg, process_member_link)

    elif call.data == "start_service":
        msg = bot.send_message(chat_id, "🔗 Jis Group/Channel ki Voice Chat (VC) me anti-drop service chalani hai, uska link bhejein:")
        bot.register_next_step_handler(msg, process_service_link)

    elif call.data == "view_services":
        show_active_services(chat_id)

    elif call.data == "stop_service":
        msg = bot.send_message(chat_id, "🛑 Jis link ki service band karni hai, uska link ya username yahan bhejein:")
        bot.register_next_step_handler(msg, process_stop_link)


def process_phone_number(message):
    chat_id = message.chat.id
    phone = message.text.strip()
    user_temp_data[chat_id] = {"phone": phone}

    client = TelegramClient(StringSession(), API_ID, API_HASH)

    async def send_code():
        await client.connect()
        result = await client.send_code_request(phone)
        user_temp_data[chat_id]["phone_code_hash"] = result.phone_code_hash
        user_temp_data[chat_id]["client"] = client

    try:
        asyncio.run(send_code())
        msg = bot.send_message(chat_id, "📨 OTP aapke Telegram par bhej diya gaya hai.\nKripya OTP yahan enter karein (jaise: `12345`):")
        bot.register_next_step_handler(msg, process_otp_code)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)}")


def process_otp_code(message):
    chat_id = message.chat.id
    code = message.text.strip()
    phone = user_temp_data.get(chat_id, {}).get("phone")
    phone_code_hash = user_temp_data.get(chat_id, {}).get("phone_code_hash")
    client = user_temp_data.get(chat_id, {}).get("client")

    async def sign_in():
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            return "2FA"
        return "SUCCESS"

    try:
        status = asyncio.run(sign_in())
        if status == "SUCCESS":
            session_str = client.session.save()
            clean_phone = phone.replace("+", "")
            saved_sessions[clean_phone] = session_str
            save_sessions_db(saved_sessions)
            asyncio.run(client.disconnect())
            bot.send_message(chat_id, f"✅ Account **{phone}** safalpurvak login hokar permanently save ho gaya hai!", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "⚠️ Account par Two-Step Verification (2FA password) laga hai.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Login fail ho gaya: {str(e)}")


def process_name_phone(message):
    chat_id = message.chat.id
    phone = message.text.strip().replace("+", "")
    if phone not in saved_sessions:
        bot.send_message(chat_id, "❌ Yeh phone number saved sessions list me nahi mila!")
        return
    user_temp_data[chat_id] = {"target_phone": phone}
    msg = bot.send_message(chat_id, "✏️ Ab is ID ke liye naya **First Name** bhejein:")
    bot.register_next_step_handler(msg, process_new_first_name)


def process_new_first_name(message):
    chat_id = message.chat.id
    first_name = message.text.strip()
    user_temp_data[chat_id]["first_name"] = first_name
    msg = bot.send_message(chat_id, "✏️ Ab naya **Last Name** bhejein (Agar nahi rakhna toh `0` ya `skip` likhein):")
    bot.register_next_step_handler(msg, process_new_last_name)


def process_new_last_name(message):
    chat_id = message.chat.id
    last_name = message.text.strip()
    if last_name.lower() in ["0", "skip"]:
        last_name = ""
    
    phone = user_temp_data.get(chat_id, {}).get("target_phone")
    first_name = user_temp_data.get(chat_id, {}).get("first_name")
    session_str = saved_sessions.get(phone)

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)

    async def update_name():
        await client.connect()
        if await client.is_user_authorized():
            await client(UpdateProfileRequest(first_name=first_name, last_name=last_name))
            await client.disconnect()
            return True
        await client.disconnect()
        return False

    try:
        success = asyncio.run(update_name())
        if success:
            bot.send_message(chat_id, f"✅ Account `+{phone}` ka naam badal kar **{first_name} {last_name}** kar diya gaya hai!", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "❌ Account authorized nahi hai.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)}")


def get_valid_sessions():
    return list(saved_sessions.keys())


def process_member_link(message):
    chat_id = message.chat.id
    target_link = message.text.strip()
    sessions = get_valid_sessions()
    if not sessions:
        bot.send_message(chat_id, "📭 Abhi tak koi bhi valid ID add nahi hai.")
        return
    user_temp_data[chat_id] = {"target_link": target_link}
    
    id_list_str = "".join([f"{idx}. `+{s}`\n" for idx, s in enumerate(sessions, 1)])
    msg = bot.send_message(
        chat_id,
        f"📋 **Total Valid IDs ({len(sessions)}):**\n{id_list_str}\n\nKitne accounts se members add karwane hain? (1 se lekar `{len(sessions)}` tak number dalein):",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_member_count)


def process_member_count(message):
    chat_id = message.chat.id
    try:
        count = int(message.text.strip())
    except ValueError:
        bot.send_message(chat_id, "❌ Kripya sahi number dalein!")
        return
    target_link = user_temp_data.get(chat_id, {}).get("target_link")
    sessions = get_valid_sessions()
    if count > len(sessions):
        count = len(sessions)
    bot.send_message(chat_id, f"⏳ **1 se {count}** tak ke accounts se members add kiye ja rahe hain...")
    asyncio.run(execute_bulk_members_add(chat_id, target_link, sessions[:count]))


async def execute_bulk_members_add(chat_id, target_link, selected_sessions):
    success_count = 0
    fail_count = 0
    for phone in selected_sessions:
        client = TelegramClient(StringSession(saved_sessions[phone]), API_ID, API_HASH)
        try:
            await client.connect()
            if await client.is_user_authorized():
                clean_link = target_link.replace("https://t.me/", "").replace("@", "")
                if "+" in clean_link or "joinchat/" in clean_link:
                    hash_val = clean_link.replace("+", "").replace("joinchat/", "").replace("https://t.me/", "")
                    await client(ImportChatInviteRequest(hash_val))
                else:
                    await client(JoinChannelRequest(clean_link))
                success_count += 1
            else:
                fail_count += 1
            await client.disconnect()
            await asyncio.sleep(0.5)
        except UserAlreadyParticipantError:
            success_count += 1
            await client.disconnect()
        except Exception:
            fail_count += 1
            if client.is_connected():
                await client.disconnect()
    bot.send_message(chat_id, f"✅ **Members Add Task Completed!**\n\n🟢 Safal: **{success_count}**\n🔴 Fail: **{fail_count}**", parse_mode="Markdown")


def process_service_link(message):
    chat_id = message.chat.id
    target_link = message.text.strip()
    sessions = get_valid_sessions()
    if not sessions:
        bot.send_message(chat_id, "📭 Abhi tak koi bhi valid ID add nahi hai.")
        return
    user_temp_data[chat_id] = {"target_link": target_link}
    
    id_list_str = "".join([f"{idx}. `+{s}`\n" for idx, s in enumerate(sessions, 1)])
    msg = bot.send_message(
        chat_id,
        f"📋 **Total Valid IDs ({len(sessions)}):**\n{id_list_str}\n\nKitne accounts se service chalani hai? (1 se lekar `{len(sessions)}` tak dalein):",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_service_count)


def process_service_count(message):
    chat_id = message.chat.id
    try:
        count = int(message.text.strip())
    except ValueError:
        bot.send_message(chat_id, "❌ Kripya sahi number dalein!")
        return

    target_link = user_temp_data.get(chat_id, {}).get("target_link")
    sessions = get_valid_sessions()
    if count > len(sessions):
        count = len(sessions)

    norm_link = target_link.strip()
    if norm_link in active_services:
        bot.send_message(chat_id, "⚠️ Is link par service pehle se active hai!")
        return

    bot.send_message(chat_id, f"🚀 **1 se {count}** accounts ke liye Multi-Channel 24/7 Anti-Drop VC service shuru kar di gayi hai!", parse_mode="Markdown")

    stop_event = threading.Event()
    active_services[norm_link] = {"count": count, "stop_event": stop_event, "sessions": sessions[:count]}

    t = threading.Thread(
        target=run_service_thread,
        args=(norm_link, sessions[:count], stop_event),
    )
    t.daemon = True
    t.start()


def run_service_thread(target_link, selected_sessions, stop_event):
    asyncio.run(start_anti_drop_service(target_link, selected_sessions, stop_event))


async def start_anti_drop_service(target_link, selected_sessions, stop_event):
    tasks = [
        manage_anti_drop_account(phone, target_link, stop_event)
        for phone in selected_sessions
    ]
    await asyncio.gather(*tasks)


async def manage_anti_drop_account(phone, target_link, stop_event):
    client = TelegramClient(StringSession(saved_sessions[phone]), API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return

        entity = await client.get_entity(target_link)

        # Join Group/Channel if not joined
        try:
            clean_link = target_link.replace("https://t.me/", "").replace("@", "")
            if "+" in clean_link or "joinchat/" in clean_link:
                hash_val = clean_link.replace("+", "").replace("joinchat/", "").replace("https://t.me/", "")
                await client(ImportChatInviteRequest(hash_val))
            else:
                await client(JoinChannelRequest(clean_link))
        except Exception:
            pass

        # Reaction Handler
        @client.on(events.NewMessage(chats=entity))
        async def handle_new_message(event):
            try:
                await client.send_read_acknowledge(entity, event.message)
                reactions_list = ["👍", "❤️", "🔥", "👏", "🎉", "😍", "⚡", "💯"]
                chosen_reaction = random.choice(reactions_list)
                await client(
                    SendReactionRequest(
                        peer=entity,
                        msg_id=event.id,
                        reaction=[ReactionEmoji(emoticon=chosen_reaction)],
                    )
                )
            except Exception:
                pass

        # Super-Robust VC Anti-Drop Loop (Every 5-6 seconds refresh / auto-rejoin)
        while not stop_event.is_set():
            try:
                full_chat = await client(functions.channels.GetFullChannelRequest(channel=entity))
                call = full_chat.full_chat.call

                if call:
                    random_ssrc = random.randint(100000, 2147483647)
                    muted_payload = '{"muted": true, "video_stopped": true, "ssrc": ' + str(random_ssrc) + '}'
                    
                    await client(
                        functions.phone.JoinGroupCallRequest(
                            call=call,
                            join_as=await client.get_me(),
                            params=DataJSON(data=muted_payload),
                            muted=True,
                            video_stopped=True,
                        )
                    )
                    print(f"[VC ACTIVE/RE-JOINED] +{phone} refreshed VC connection.")
            except Exception as e:
                print(f"[VC RECONNECT INFO] +{phone}: {e}")

            # 5 se 6 seconds delay between requests as requested
            sleep_time = random.uniform(5.0, 6.0)
            await asyncio.sleep(sleep_time)

        await client.disconnect()
    except Exception as e:
        print(f"[CLIENT FATAL ERROR] +{phone}: {e}")
        if client.is_connected():
            await client.disconnect()


def show_active_services(chat_id):
    if not active_services:
        bot.send_message(chat_id, "📭 Abhi koi bhi 24/7 service active nahi hai.")
        return
    text = "📊 **Active Services List:**\n\n"
    for link, info in active_services.items():
        text += f"• **Link:** `{link}`\n  **Active Accounts:** `{info['count']}`\n\n"
    bot.send_message(chat_id, text, parse_mode="Markdown")


def process_stop_link(message):
    chat_id = message.chat.id
    target_link = message.text.strip()
    
    found_key = None
    for key in list(active_services.keys()):
        if target_link in key or key in target_link:
            found_key = key
            break

    if found_key:
        active_services[found_key]["stop_event"].set()
        del active_services[found_key]
        bot.send_message(chat_id, f"🛑 **Service Stopped Successfully** for link: `{target_link}`", parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "❌ Is link par koi bhi active service nahi mili! Kripya sahi link dalein.")


def show_ids_list(chat_id):
    sessions = get_valid_sessions()
    if not sessions:
        bot.send_message(chat_id, "📭 Abhi tak koi bhi valid ID add nahi ki gayi hai.")
        return
    text = f"📋 **Saved Telegram Accounts (Total: {len(sessions)}):**\n\n"
    for idx, s in enumerate(sessions, 1):
        text += f"{idx}. `+{s}`\n"
    bot.send_message(chat_id, text, parse_mode="Markdown")


def run_admin_bot():
    admin_bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    print("Starting Bots...")
    t = threading.Thread(target=run_admin_bot)
    t.daemon = True
    t.start()

    print("Main Bot started successfully...")
    bot.infinity_polling(skip_pending=True)
