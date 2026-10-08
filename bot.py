import os
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")  # твой ID

if not BOT_TOKEN:
    raise ValueError("Нет BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# Кнопки
keyboard = [["📦 Заказать курьера"], ["/id", "/help"]]
markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Привет! Бот Час-Пик работает ✅\n\nТвой ID: {update.effective_user.id}\nНажми '📦 Заказать курьера' чтобы сделать заказ",
        reply_markup=markup
    )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Твой ID: {update.effective_user.id}\nЮзернейм: @{update.effective_user.username}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Нажми 📦 Заказать курьера и напиши адрес и телефон\nАдмин: /admin")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("Ты не админ ❌")
        return
    await update.message.reply_text(f"Ты админ ✅\nТвой ID: {ADMIN_ID}\nВсе заказы будут приходить сюда в личку.")

async def handle_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📦 Заказать курьера":
        await update.message.reply_text("Напиши адрес откуда и куда, и свой номер телефона.\nПример:\nЗабрать с ул. Абая 1, доставить на ул. Лермонтова 5. Тел: +77001234567")
        return

    # Считаем что это заказ
    user = update.effective_user
    order_text = f"🔔 НОВЫЙ ЗАКАЗ КУРЬЕРА!\n\n👤 Клиент: @{user.username} ({user.full_name})\n🆔 ID: {user.id}\n📞 Заказ:\n{text}"

    # 1. Клиенту
    await update.message.reply_text("✅ Заказ принят! Курьер свяжется с вами в течение 5 минут.", reply_markup=markup)
    
    # 2. Админу
    if ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_ID), text=order_text)
            print(f"Заказ отправлен админу {ADMIN_ID}")
        except Exception as e:
            print(f"Не смог отправить админу: {e}")
            await update.message.reply_text(f"⚠️ Админ не получил заказ. Проверь ADMIN_ID. Ошибка: {e}")
    else:
        print(f"Новый заказ (нет ADMIN_ID): {order_text}")

if __name__ == "__main__":
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_id))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order))
    
    print("Bot started polling...")
    app.run_polling()
