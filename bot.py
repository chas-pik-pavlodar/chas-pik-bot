import os
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

Thread(target=run_dummy_server, daemon=True).start()
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = "8933761066:AAERcm7bd2ijM0RJd-5Twrlw1C0rMMGuS4s"
ADMIN_USERNAME = "Volkamagen979"
ADMIN_EMAIL = "satirikon2212@gmail.com"

logging.basicConfig(level=logging.INFO)

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

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_order'):
        order_text = update.message.text
        user = update.message.from_user
        text_for_admin = f"Новый заказ от @{user.username} ({user.id}):\n{order_text}"
        # тут можно отправить админу
        await update.message.reply_text(f"Спасибо! Ваш заказ принят: {order_text}\nМы свяжемся с вами. Админ {ADMIN_USERNAME}")
        context.user_data['awaiting_order'] = False
    else:
        await update.message.reply_text("Нажмите /start чтобы начать")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
