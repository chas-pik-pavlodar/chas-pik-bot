import os, logging, threading, asyncio, sqlite3
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.environ.get("TOKEN")
KASPI_NUMBER = "+7 700 767 57 39"
KASPI_NAME = "Час-Пик"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1218877896"))
ADMIN_IDS = [1218877896, ADMIN_ID]
OPERATOR_IDS = [1218877896, ADMIN_ID]
PRICE_DELIVERY = 700
DB = "database.db"

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running!"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, client_username TEXT, address_from TEXT, address_to TEXT, price INTEGER, status TEXT DEFAULT 'new')")
    c.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, username TEXT, status TEXT DEFAULT 'free')")
    conn.commit()
    conn.close()

class OrderForm(StatesGroup):
    from_address = State()
    to_address = State()

def client_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📦 Сделать заказ")],[KeyboardButton(text="🚚 Стать курьером")]], resize_keyboard=True)

def operator_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📋 Заказы")],[KeyboardButton(text="📦 Сделать заказ")]], resize_keyboard=True)

@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    init_db()
    if m.from_user.id in OPERATOR_IDS:
        await m.answer("Оператор-панель Час-Пик Павлодар 🚚", reply_markup=operator_kb())
    else:
        await m.answer("Привет! Час-Пик Павлодар на связи! 🚚\nБыстрая доставка по городу 700тг", reply_markup=client_kb())

@dp.message(F.text == "🚚 Стать курьером")
async def become_courier(m: Message, state: FSMContext):
    await state.clear()
    try:
        init_db()
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (m.from_user.id,)) if False else None
        c.execute("INSERT OR IGNORE INTO couriers (user_id, username, status) VALUES (?,?, 'free')", (m.from_user.id, m.from_user.username or m.from_user.first_name))
        conn.commit()
        conn.close()
        await m.answer("✅ Заявка принята! Ты теперь курьер Час-Пик!\n\nОжидай заказы, админ напишет тебе.", reply_markup=client_kb())
        # Уведомление админу
        try:
            await bot.send_message(ADMIN_ID, f"🆕 Новый курьер: @{m.from_user.username} | {m.from_user.first_name} | ID: {m.from_user.id}")
        except:
            pass
    except Exception as e:
        logging.error(f"become_courier error: {e}")
        await m.answer(f"Ошибка, напиши админу: {e}")

@dp.message(F.text == "📦 Сделать заказ")
async def order_start(m: Message, state: FSMContext):
    await state.set_state(OrderForm.from_address)
    await m.answer("Откуда забрать? Напиши адрес:")

@dp.message(OrderForm.from_address)
async def order_from(m: Message, state: FSMContext):
    await state.update_data(from_addr=m.text)
    await state.set_state(OrderForm.to_address)
    await m.answer("Куда доставить? Напиши адрес:")

@dp.message(OrderForm.to_address)
async def order_to(m: Message, state: FSMContext):
    data = await state.get_data()
    from_addr = data.get("from_addr")
    to_addr = m.text
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO orders (client_id, client_username, address_from, address_to, price) VALUES (?,?,?,?,?)", (m.from_user.id, m.from_user.username, from_addr, to_addr, PRICE_DELIVERY))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    await state.clear()
    await m.answer(f"✅ Заказ #{order_id} принят!\nОткуда: {from_addr}\nКуда: {to_addr}\nДоставка: {PRICE_DELIVERY}тг\n\nОплата Kaspi: {KASPI_NUMBER} ({KASPI_NAME})\n\nКурьер скоро свяжется!", reply_markup=client_kb())
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Принять", callback_data=f"take_{order_id}")]])
        await bot.send_message(ADMIN_ID, f"🆕 Заказ #{order_id}\nОт: {from_addr}\nДо: {to_addr}\nКлиент: @{m.from_user.username} {m.from_user.id}", reply_markup=kb)
    except:
        pass

@dp.message(F.text == "📋 Заказы")
async def list_orders(m: Message):
    if m.from_user.id not in OPERATOR_IDS:
        return
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, address_from, address_to FROM orders WHERE status='new' ORDER BY id DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await m.answer("Нет новых заказов")
        return
    text = "📋 Новые заказы:\n\n"
    for r in rows:
        text += f"#{r[0]}: {r[1]} -> {r[2]}\n"
    await m.answer(text)

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cq: CallbackQuery):
    order_id = cq.data.split("_")[1]
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status='taken' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    await cq.message.edit_text(f"✅ Заказ #{order_id} принят вами")
    await cq.answer("Принято!")

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def run_bot():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())

