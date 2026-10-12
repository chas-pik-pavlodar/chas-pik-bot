import os, logging, threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

logging.basicConfig(level=logging.INFO)

# --- Маленький сайт для Render (чтобы был бесплатным) ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot Час-Пик Павлодар на связи!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# --- Твой бот ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Бот Час-Пик Павлодар на связи.")

def main():
    if not BOT_TOKEN:
        raise ValueError("Нет TOKEN в переменных окружения")
    
    # Запускаем сайт в фоне
    threading.Thread(target=run_flask, daemon=True).start()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("started")
    app.run_polling()

if __name__ == "__main__":
    main()
