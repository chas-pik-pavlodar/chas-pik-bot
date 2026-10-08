import os
import logging
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

Thread(target=run_dummy_server, daemon=True).start()

# Берем токен из настроек Render
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Нет BOT_TOKEN в Environment!")

ADMIN_USERNAME = "Volkamagen979"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🛒 Создать заказ", callback_data='create_order')],
        [InlineKeyboardButton("🚚 Стать курьером", callback_data='courier')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Добро пожаловать в Час-Пик Павлодар! Выберите действие:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'create_order':
        await query.edit_message_text("Напишите что вы хотите заказать и адрес доставки:")
        context.user_data['awaiting_order'] = True
    elif query.data == 'courier':
        await query.edit_message_text("Чтобы стать курьером, напишите ваше имя и номер телефона:")
        context.user_data['awaiting_courier'] = True

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = update.message.text
    
    if context.user_data.get('awaiting_order'):
        logger.info(f"Новый заказ от @{user.username}: {text}")
        await update.message.reply_text(f"Спасибо! Заказ принят:\n{text}\n\nМы свяжемся с вами. Админ @{ADMIN_USERNAME}")
        context.user_data['awaiting_order'] = False
    elif context.user_data.get('awaiting_courier'):
        logger.info(f"Новый курьер @{user.username}: {text}")
        await update.message.reply_text(f"Спасибо, {text}! Заявка курьера принята.")
        context.user_data['awaiting_courier'] = False
    else:
        await update.message.reply_text("Нажмите /start чтобы начать")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    logger.info("Bot started polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
