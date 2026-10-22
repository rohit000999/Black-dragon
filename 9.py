import sys
import random
import logging
import httpx
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = "8896458093:AAEEvYTrT5nUdgpTAC8UrAs07viGcTtANMY"
TARGET_CHANNEL_ID = -1003823983616

SCHEDULE_HOURS = list(range(8, 23))

BETS_POOL = {
    "SMALL": ["1,3", "2,4", "0,2"],
    "BIG": ["5,7", "6,8", "7,9"]
}

state = {
    "is_running": False,
    "last_id": None,
    "last_side": None,
    "last_pair": None,
    "session_message_id": None,
    "history_text": "",
    "bet_count": 0
}

async def fetch_api_data():
    url = 'https://draw.ar-lottery01.com/WinGo/WinGo_1M/GetHistoryIssuePage.json'
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        return response.json()

def calculate_prediction(json_data):
    trend = [
        "BIG" if int(x["number"]) >= 5 else "SMALL"
        for x in json_data["data"]["list"][:3]
    ]
    next_side = "BIG" if trend.count("BIG") > 1 else "SMALL"
    current_pool = BETS_POOL[next_side]
    random_pair = random.choice(current_pool)
    return next_side, random_pair

def format_time_12h(hour):
    if hour == 0:
        return "12 : 00 AM"
    elif hour == 12:
        return "12 : 00 PM"
    elif hour > 12:
        return f"{hour - 12:02d} : 00 PM"
    else:
        return f"{hour:02d} : 00 AM"

async def send_end_notification(bot, next_hour):
    if next_hour is not None:
        next_time_str = format_time_12h(next_hour)
        msg = f"🏁 **ABHI KA SESSION KHATAM**\n\nNEXT SESSION **{next_time_str}** par start hoga, sabhi ready rehna ok."
    else:
        msg = f"🏁 **AAJ KE SARE SESSIONS KHATAM HO GAYE HAIN!**\nKAL PHIR SE **08 : 00 AM** PAR START HOGA."
    
    await bot.send_message(chat_id=TARGET_CHANNEL_ID, text=msg, parse_mode="Markdown")

async def run_session(bot, current_hour):
    global state
    state["is_running"] = True
    state["last_id"] = None
    state["last_side"] = None
    state["last_pair"] = None
    state["session_message_id"] = None
    state["history_text"] = ""
    state["bet_count"] = 0

    while state["bet_count"] < 15:
        try:
            json_data = await fetch_api_data()
            latest = json_data["data"]["list"][0]
            latest_id = latest["issueNumber"]
            latest_num = str(latest["number"])
            actual_side = "BIG" if int(latest_num) >= 5 else "SMALL"

            if state["last_id"] != latest_id:
                if state["last_id"] is not None:
                    pair_list = state["last_pair"].split(",")
                    is_jackpot = latest_num in pair_list
                    is_side_win = (state["last_side"] == actual_side)

                    if is_jackpot:
                        status = "JACKPOT WIN🏆🏆"
                    elif is_side_win:
                        status = "WIN✅️✅️"
                    else:
                        status = "LOSS❌️❌️"

                    last_period_short = state["last_id"][-3:]
                    state["history_text"] += f"{last_period_short} = {state['last_side']} {state['last_pair']} = {status}\n"
                    state["bet_count"] += 1

                if state["bet_count"] < 15:
                    next_side, next_pair = calculate_prediction(json_data)
                    state["last_id"] = latest_id
                    state["last_side"] = next_side
                    state["last_pair"] = next_pair

                    next_period_short = str(int(latest_id) + 1)[-3:]
                    current_view = state["history_text"] + f"{next_period_short} = {next_side} {next_pair}"

                    if state["session_message_id"] is None:
                        msg = await bot.send_message(
                            chat_id=TARGET_CHANNEL_ID,
                            text=current_view
                        )
                        state["session_message_id"] = msg.message_id
                    else:
                        await bot.edit_message_text(
                            chat_id=TARGET_CHANNEL_ID,
                            message_id=state["session_message_id"],
                            text=current_view
                        )
                else:
                    await bot.edit_message_text(
                        chat_id=TARGET_CHANNEL_ID,
                        message_id=state["session_message_id"],
                        text=state["history_text"].strip()
                    )

        except Exception as e:
            logging.error(f"Error in prediction cycle: {e}")

        await asyncio.sleep(2)

    state["is_running"] = False

    next_index = SCHEDULE_HOURS.index(current_hour) + 1
    next_hour = SCHEDULE_HOURS[next_index] if next_index < len(SCHEDULE_HOURS) else None
    await send_end_notification(bot, next_hour)

async def main_scheduler(bot):
    last_run_hour = -1
    last_prenotif_hour = -1
    while True:
        now = datetime.now()
        h = now.hour
        m = now.minute

        upcoming_hour = h + 1
        if m == 55 and upcoming_hour != last_prenotif_hour and upcoming_hour in SCHEDULE_HOURS:
            last_prenotif_hour = upcoming_hour
            time_str = format_time_12h(upcoming_hour)
            pre_msg = f"🚨 **READY HO JAO SABHI LOG!**\n\n**{time_str}** par bet start hoga, sabhi ready rehna ok."
            try:
                await bot.send_message(chat_id=TARGET_CHANNEL_ID, text=pre_msg, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Error sending pre-notification: {e}")

        if m == 0 and h != last_run_hour and h in SCHEDULE_HOURS:
            last_run_hour = h
            asyncio.create_task(run_session(bot, h))

        await asyncio.sleep(15)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Dragon Prediction Bot Active & Scheduled!")

async def post_init(application):
    asyncio.create_task(main_scheduler(application.bot))

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_cmd))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
