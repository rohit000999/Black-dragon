import os
import threading
from flask import Flask
import telebot

TOKEN = "8875427334:AAFZoBx5aZSaejCulhYIR1QhwV-1G1UBSu8"
SOURCE_CHANNEL_ID = -1003823983616
TARGET_CHANNEL_ID = -1004318022115

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot is running!"

@bot.channel_post_handler(func=lambda message: True)
def forward_posts(message):
    if message.chat.id == SOURCE_CHANNEL_ID:
        try:
            bot.forward_message(TARGET_CHANNEL_ID, message.chat.id, message.message_id)
        except Exception as e:
            print(f"Error: {e}")

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
