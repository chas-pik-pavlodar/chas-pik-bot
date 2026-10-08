import os, asyncio, logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

logging.basicConfig(level=logging.INFO)

kb = [["📦 Заказать курьера"], ["/id", "/admin"]]
markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update, context):
    await update.message.reply_text(f"Бот работает ✅\nТвой ID: {update.effective_user.id}", reply_markup=markup)

async def get_id(update, context):
    await update.message.reply_text(f"ID: {update.effective_user.id}")

async def admin_cmd(update, context):
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("Ты не админ")
        return
    await update.message.reply_text(f"Ты админ ✅ ID: {ADMIN_ID}")

async def order(update, context):
    if update.message.text == "📦 Заказать курьера":
        await update.message.reply_text("Напиши адрес и телефон:")
        return
    txt = update.message.text
    user = update.effective_user
    await update.message.reply_text("✅ Заказ принят!")
    if ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_ID), text=f"🔔 НОВЫЙ ЗАКАЗ\nОт @{user.username} {user.full_name}\nID:{user.id}\n\n{txt}")
        except Exception as e:
            print(e)

if __name__ == "__main__":
    try: asyncio.get_event_loop()
    except: asyncio.set_event_loop(asyncio.new_event_loop())
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_id))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, order))
    print("Bot started")
    app.run_polling()
