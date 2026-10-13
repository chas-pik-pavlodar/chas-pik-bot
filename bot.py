import os, logging, threading, asyncio, sqlite3
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

BOT_TOKEN = os.environ.get("TOKEN")
KASPI_NUMBER = "+7 700 767 57 34"
KASPI_NAME = "Час-Пик"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1218877096"))
ADMIN_IDS = [1218877096, ADMIN_ID]
OPERATOR_IDS = [1218877096, ADMIN_ID]
PRICE_DELIVERY = 700

logging.basicConfig(level=logging.INFO)
flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Bot Chas-Pik Pavlodar na svyazi!"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
DB = "chas_pik.db"

def init_db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, role TEXT DEFAULT 'client', is_online INTEGER DEFAULT 0)")
    con.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, address TEXT, what TEXT, price INTEGER, status TEXT, courier_id INTEGER, photo_report TEXT, check_file TEXT)")
    con.commit(); con.close()

class OrderForm(StatesGroup):
    address = State(); what = State(); wait_check = State(); wait_amount = State(); wait_photo_report = State()

def client_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🛒 Сделать заказ")],[KeyboardButton(text="📦 Мои заказы")]], resize_keyboard=True)
def courier_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🟢 Я на линии"), KeyboardButton(text="🔴 Оффлайн")],[KeyboardButton(text="📋 Свободные заказы")]], resize_keyboard=True)
def operator_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🆕 Новые"), KeyboardButton(text="💳 Чеки")],[KeyboardButton(text="🔄 В работе")]], resize_keyboard=True)

@dp.message(Command("start"))
async def start(m: Message):
    con = sqlite3.connect(DB); con.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (m.from_user.id,)); con.commit(); con.close()
    if m.from_user.id in ADMIN_IDS:
        await m.answer("Панель оператора 👩‍💼 - Твой Kaspi 87007675734", reply_markup=operator_kb())
    else:
        await m.answer(f"Час-Пик доставка {PRICE_DELIVERY}тг. Твои данные уже внутри.", reply_markup=client_kb())
@dp.message(F.text == "🚚 Стать курьером")
async def become_courier(m: Message):
    
        con = sqlite3.connect(DB); cur = con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY, courier_id INTEGER UNIQUE)")
        cur.execute("INSERT OR IGNORE INTO couriers (courier_id) VALUES (?)", (m.from_user.id,))
        con.commit(); con.close()
    await m.answer("✅ Ты теперь курьер! Жди заказы. Если появится заказ - я напишу.", reply_markup=courier_kb)
@dp.message(F.text == "🛒 Сделать заказ")
async def new_order(m: Message, state: FSMContext):
    await state.set_state(OrderForm.address); await m.answer("Адрес куда везти? Текст или геолокация 📍")
@dp.message(OrderForm.address)
async def get_addr(m: Message, state: FSMContext):
    addr = m.text or (f"{m.location.latitude},{m.location.longitude}" if m.location else "Адрес")
    await state.update_data(address=addr); await state.set_state(OrderForm.what); await m.answer("Что везем?")
@dp.message(OrderForm.what)
async def get_what(m: Message, state: FSMContext):
    data = await state.get_data()
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("INSERT INTO orders (client_id, address, what, price, status) VALUES (?,?,?,?,?)",(m.from_user.id, data['address'], m.text or "Товар", PRICE_DELIVERY, "wait_pay"))
    oid = cur.lastrowid; con.commit(); con.close(); await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{oid}")]])
    await m.answer(f"Заказ #{oid}\n💳 Kaspi: {KASPI_NUMBER} ({KASPI_NAME})\nСумма: {PRICE_DELIVERY}тг РОВНО\nКоммент: {oid}\n\nПришли чек любым способом: фото, PDF (Поделиться чеком) или пересылку", reply_markup=kb)

@dp.callback_query(F.data.startswith("paid_"))
async def paid_btn(c: CallbackQuery, state: FSMContext):
    oid = c.data.split("_")[1]; await state.set_state(OrderForm.wait_amount); await state.update_data(order_id=oid)
    await c.message.answer(f"#{oid} - напиши сумму перевода цифрами"); await c.answer()
@dp.message(OrderForm.wait_amount)
async def get_amount(m: Message, state: FSMContext):
    await state.update_data(amount=m.text); await state.set_state(OrderForm.wait_check)
    await m.answer("Теперь чек: фото, PDF файл или пересылка из Kaspi")
@dp.message(OrderForm.wait_check, F.photo | F.document | F.text)
async def get_check(m: Message, state: FSMContext):
    data = await state.get_data(); oid = data['order_id']
    file_id = m.photo[-1].file_id if m.photo else m.document.file_id if m.document else ""
    con = sqlite3.connect(DB); con.execute("UPDATE orders SET status='check_pending', check_file=? WHERE id=?", (file_id, oid)); con.commit(); con.close()
    await state.clear(); await m.answer(f"Чек #{oid} получен, оператор проверит", reply_markup=client_kb())
    for op_id in OPERATOR_IDS:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"confirm_{oid}")]])
            if m.photo: await bot.send_photo(op_id, file_id, caption=f"ЧЕК #{oid} Сумма {data['amount']}", reply_markup=kb)
            elif m.document: await bot.send_document(op_id, file_id, caption=f"PDF ЧЕК #{oid}", reply_markup=kb)
            else: await bot.send_message(op_id, f"ЧЕК #{oid}: {m.text}", reply_markup=kb)
        except: pass

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_pay(c: CallbackQuery):
    oid = c.data.split("_")[1]
    con = sqlite3.connect(DB); con.execute("UPDATE orders SET status='free' WHERE id=?", (oid,))
    couriers = con.execute("SELECT user_id FROM users WHERE role='courier' AND is_online=1").fetchall()
    order = con.execute("SELECT address, what, price FROM orders WHERE id=?", (oid,)).fetchone(); con.close()
    await c.message.edit_text(f"#{oid} подтвержден! Рассылаю ВСЕМ {len(couriers)} курьерам")
    for (cid,) in couriers:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗺️ Маршрут 2ГИС/Яндекс", callback_data=f"route_{oid}"), InlineKeyboardButton(text="✅ Взять", callback_data=f"take_{oid}")]])
            await bot.send_message(cid, f"🆕 СВОБОДНЫЙ #{oid}\nАдрес: {order[0]}\nЧто: {order[1]}\n{order[2]}тг", reply_markup=kb)
        except: pass

@dp.callback_query(F.data.startswith("take_"))
async def take_order(c: CallbackQuery):
    oid = c.data.split("_")[1]
    con = sqlite3.connect(DB); st = con.execute("SELECT status FROM orders WHERE id=?", (oid,)).fetchone()
    if not st or st[0]!="free": await c.answer("Уже забрали!", show_alert=True); con.close(); return
    con.execute("UPDATE orders SET status='taken', courier_id=? WHERE id=?", (c.from_user.id, oid)); con.commit(); con.close()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 Фотоотчет обязателен", callback_data=f"photoreport_{oid}")],[InlineKeyboardButton(text="✅ Доставил", callback_data=f"delivered_{oid}")]])
    await c.message.edit_text(f"Ты взял #{oid}. Сделай фото у двери!", reply_markup=kb)

@dp.callback_query(F.data.startswith("route_"))
async def route(c: CallbackQuery):
    oid = c.data.split("_")[1]
    con = sqlite3.connect(DB); addr = con.execute("SELECT address FROM orders WHERE id=?", (oid,)).fetchone()[0]; con.close()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="2ГИС", url=f"https://2gis.kz/pavlodar/search/{addr}"), InlineKeyboardButton(text="Яндекс", url=f"https://yandex.kz/maps/?text={addr}")],[InlineKeyboardButton(text="Google", url=f"https://www.google.com/maps/search/{addr}")]])
    await c.message.answer(f"Ехать сюда: {addr}\nЖми свою карту:", reply_markup=kb); await c.answer()

@dp.callback_query(F.data.startswith("photoreport_"))
async def need_photo(c: CallbackQuery, state: FSMContext):
    await state.set_state(OrderForm.wait_photo_report); await state.update_data(order_id=c.data.split("_")[1])
    await c.message.answer("Скинь фотоотчет 📸 - фото заказа у двери"); await c.answer()
@dp.message(OrderForm.wait_photo_report, F.photo)
async def save_photo(m: Message, state: FSMContext):
    oid = (await state.get_data())['order_id']; fid = m.photo[-1].file_id
    con = sqlite3.connect(DB); con.execute("UPDATE orders SET photo_report=? WHERE id=?", (fid, oid)); con.commit(); con.close()
    await state.clear(); await m.answer("Фото сохранено, теперь жми ✅ Доставил")

@dp.callback_query(F.data.startswith("delivered_"))
async def delivered(c: CallbackQuery):
    oid = c.data.split("_")[1]
    con = sqlite3.connect(DB); ph = con.execute("SELECT photo_report, client_id FROM orders WHERE id=?", (oid,)).fetchone()
    if not ph[0]: await c.answer("Сначала скинь ФОТООТЧЕТ!", show_alert=True); con.close(); return
    con.execute("UPDATE orders SET status='done' WHERE id=?", (oid,)); con.commit(); con.close()
    await c.message.edit_text(f"✅ #{oid} доставлен с фото!"); await bot.send_message(ph[1], f"✅ Заказ #{oid} доставлен! Фотоотчет есть.")

@dp.message(F.text == "🟢 Я на линии")
async def online(m: Message):
    con = sqlite3.connect(DB); con.execute("UPDATE users SET is_online=1, role='courier' WHERE user_id=?", (m.from_user.id,)); con.commit(); con.close()
    await m.answer("Ты на линии, заказы будут прилетать всем курьерам сразу", reply_markup=courier_kb())

async def run_bot():
    init_db(); await dp.start_polling(bot)
def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    asyncio.run(run_bot())
