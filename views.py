import telebot

TOKEN = "8875427334:AAFZoBx5aZSaejCulhYIR1QhwV-1G1UBSu8"
SOURCE_CHANNEL_ID = -1003823983616
TARGET_CHANNEL_ID = -1004318022115

bot = telebot.TeleBot(TOKEN)

@bot.channel_post_handler(func=lambda message: True)
def forward_posts(message):
    if message.chat.id == SOURCE_CHANNEL_ID:
        bot.forward_message(TARGET_CHANNEL_ID, message.chat.id, message.message_id)

bot.infinity_polling()
