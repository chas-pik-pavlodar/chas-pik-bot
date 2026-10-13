import os
import logging
import threading
import asyncio
import sqlite3
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1218877896"))
DB = "database.db"

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot alive!"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, client_username TEXT, address_from TEXT, address_to TEXT, price TEXT, status TEXT DEFAULT 'new', courier_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, username TEXT)")
    conn.commit()
    conn.close()

class OrderForm(StatesGroup):
    from_address = State()
    to_address = State()
    price = State()

def client_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📦 Сделать заказ")],[KeyboardButton(text="🚚 Стать курьером")]], resize_keyboard=True)

@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    init_db()
    await m.answer("Час-Пик Павлодар работает! Жми Сделать заказ", reply_markup=client_kb())

@dp.message(F.text == "🚚 Стать курьером")
async def become_courier(m: Message):
    init_db()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username) VALUES (?,?)", (m.from_user.id, m.from_user.username or m.from_user.first_name))
    conn.commit()
    conn.close()
    await m.answer("Ты теперь курьер! Жди заказы.")
    try:
        await bot.send_message(ADMIN_ID, f"Новый курьер: @{m.from_user.username} ID {m.from_user.id}")
    except:
        pass

@dp.message(F.text == "📦 Сделать заказ")
async def order_start(m: Message, state: FSMContext):
    await state.set_state(OrderForm.from_address)
    await m.answer("Откуда забрать? Адрес:")

@dp.message(OrderForm.from_address)
async def order_from(m: Message, state: FSMContext):
    await state.update_data(from_addr=m.text)
    await state.set_state(OrderForm.to_address)
    await m.answer("Куда доставить? Адрес:")

@dp.message(OrderForm.to_address)
async def order_to(m: Message, state: FSMContext):
    await state.update_data(to_addr=m.text)
    await state.set_state(OrderForm.price)
    await m.answer("Какую цену предлагаешь? Напиши 1000 или 1500")

@dp.message(OrderForm.price)
async def order_price(m: Message, state: FSMContext):
    data = await state.get_data()
    from_addr = data.get("from_addr")
    to_addr = data.get("to_addr")
    price = m.text
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO orders (client_id, client_username, address_from, address_to, price) VALUES (?,?,?,?,?)", (m.from_user.id, m.from_user.username, from_addr, to_addr, price))
    order_id = c.lastrowid
    c.execute("SELECT user_id FROM couriers")
    couriers = c.fetchall()
    conn.commit()
    conn.close()
    await state.clear()
    await m.answer(f"Заказ #{order_id} принят! Цена {price}. Разослали курьерам.", reply_markup=client_kb())
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Взять за {price}", callback_data=f"take_{order_id}")]])
    text_c = f"ЗАКАЗ #{order_id}\nОт: {from_addr}\nДо: {to_addr}\nЦена: {price}\nКлиент: @{m.from_user.username}"
    for (cid,) in couriers:
        try:
            await bot.send_message(cid, text_c, reply_markup=kb)
        except:
            pass

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cq: CallbackQuery):
    order_id = int(cq.data.split("_")[1])
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT status, client_id, address_from, address_to, price FROM orders WHERE id=?", (order_id,))
    row = c.fetchone()
    if not row:
        await cq.answer("Не найден")
        return
    status, client_id, from_addr, to_addr, price = row
    if status!= 'new':
        await cq.answer("Уже взяли!", show_alert=True)
        conn.close()
        return
    c.execute("UPDATE orders SET status='taken', courier_id=? WHERE id=?", (cq.from_user.id, order_id))
    conn.commit()
    conn.close()
    await cq.message.edit_text(f"ТЫ ВЗЯЛ ЗАКАЗ #{order_id} за {price}")
    await cq.answer("Твой!")
    try:
        await bot.send_message(client_id, f"Твой заказ #{order_id} взял курьер @{cq.from_user.username} за {price}")
    except:
        pass

@dp.message(Command("couriers"))
async def list_couriers(m: Message):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT user_id, username FROM couriers")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await m.answer("Курьеров нет")
        return
    text = f"Курьеров: {len(rows)}\n"
    for uid, uname in rows:
        text += f"@{uname} ID {uid}\n"
    await m.answer(text)

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())

