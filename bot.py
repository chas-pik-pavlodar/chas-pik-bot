import os, logging, threading, asyncio, sqlite3, urllib.parse
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

# ТВОИ НОМЕРА - ПРОВЕРЬ ЧТО С +7
OPERATOR_PHONE = "+77771234567"
COURIER_MAIN_PHONE = "+77771234567"

HARDCODED_COURIERS = [
    (7714431728, "main_kurier", COURIER_MAIN_PHONE),
]

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
@app.route('/')
def home(): return "Bot alive!"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, client_username TEXT, address_from TEXT, address_to TEXT, what TEXT, note TEXT, price TEXT, status TEXT DEFAULT 'new', courier_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, username TEXT, phone TEXT)")
    # Миграция для старой базы - добавляем колонки если их нет
    try: c.execute("ALTER TABLE orders ADD COLUMN what TEXT")
    except: pass
    try: c.execute("ALTER TABLE orders ADD COLUMN note TEXT")
    except: pass
    try: c.execute("ALTER TABLE couriers ADD COLUMN phone TEXT")
    except: pass
    for uid, uname, phone in HARDCODED_COURIERS:
        c.execute("INSERT OR IGNORE INTO couriers (user_id, username, phone) VALUES (?,?,?)", (uid, uname, phone))
        c.execute("UPDATE couriers SET phone=? WHERE user_id=?", (phone, uid))
    conn.commit(); conn.close()

def get_earnings(courier_id):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT price FROM orders WHERE courier_id=? AND status='done'", (courier_id,))
    rows = c.fetchall(); conn.close()
    total=0
    for (p,) in rows:
        try: total+=int(''.join(filter(str.isdigit, str(p))) or 0)
        except: pass
    return total, len(rows)

class OrderForm(StatesGroup):
    from_address=State(); to_address=State(); what=State(); note=State(); price=State()
class PhotoReport(StatesGroup):
    waiting_photo=State()

def contact_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📞 Оператор {OPERATOR_PHONE}", url=f"tel:{OPERATOR_PHONE}")],
        [InlineKeyboardButton(text=f"🛵 Курьер {COURIER_MAIN_PHONE}", url=f"tel:{COURIER_MAIN_PHONE}")]
    ])
def client_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📦 Сделать заказ")],[KeyboardButton(text="🚚 Стать курьером"), KeyboardButton(text="📞 Оператор")],[KeyboardButton(text="💰 Мой заработок")]], resize_keyboard=True)
def courier_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 Обновить где я", request_location=True)],[KeyboardButton(text="✅ Я доставил - фотоотчет")],[KeyboardButton(text="💰 Мой заработок"), KeyboardButton(text="📞 Оператор")]], resize_keyboard=True)

@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear(); init_db()
    await m.answer("ЧАС ПИК Павлодар ⚡️", reply_markup=client_kb())

@dp.message(F.text=="📞 Оператор")
async def op_contact(m: Message):
    await m.answer(f"Связь:\nОператор: {OPERATOR_PHONE}\nКурьер: {COURIER_MAIN_PHONE}\n\nЖми кнопку ниже - работает только с телефона!", reply_markup=contact_kb())

@dp.message(F.text=="🚚 Стать курьером")
async def become_courier(m: Message):
    init_db()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, phone) VALUES (?,?,?)", (m.from_user.id, m.from_user.username or "kurier", COURIER_MAIN_PHONE))
    conn.commit(); conn.close()
    await m.answer("✅ Ты курьер!", reply_markup=courier_kb())

@dp.message(F.text=="💰 Мой заработок")
async def my_earn(m: Message):
    total,cnt=get_earnings(m.from_user.id)
    await m.answer(f"💰 Заработок: {cnt} заказов / {total} тг")

@dp.message(Command("fix"))
@dp.message(Command("couriers"))
async def list_couriers(m: Message):
    init_db()
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT user_id, username FROM couriers"); rows=c.fetchall(); conn.close()
    if not rows: await m.answer("Курьеров нет. Нажми Стать курьером"); return
    txt=""
    for uid,uname in rows:
        earn,cnt=get_earnings(uid)
        txt+=f"@{uname} {uid} - {cnt} зак / {earn}тг\n"
    await m.answer(f"Курьеры:\n{txt}\n\nЕсли не приходят заказы - курьер должен написать /start и стать курьером заново")

@dp.message(Command("earnings"))
async def admin_earn(m: Message):
    if m.from_user.id!=ADMIN_ID: return
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT courier_id, price, status FROM orders"); rows=c.fetchall(); conn.close()
    if not rows: await m.answer("Заказов нет"); return
    await m.answer("\n".join([f"курьер {r[0]} {r[1]}тг [{r[2]}]" for r in rows][-20:]))

@dp.message(Command("reset_orders"))
async def reset_orders(m: Message):
    if m.from_user.id!=ADMIN_ID: return
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE orders SET status='done' WHERE status='taken'")
    conn.commit(); conn.close()
    await m.answer("Все taken -> done. Теперь /couriers покажет заработок")

@dp.message(F.text=="📦 Сделать заказ")
async def order_start(m: Message, state: FSMContext):
    await state.set_state(OrderForm.from_address); await m.answer("📍 Откуда забрать?")

@dp.message(OrderForm.from_address)
async def order_from(m: Message, state: FSMContext):
    await state.update_data(from_addr=m.text); await state.set_state(OrderForm.to_address); await m.answer("🏁 Куда доставить?")

@dp.message(OrderForm.to_address)
async def order_to(m: Message, state: FSMContext):
    await state.update_data(to_addr=m.text); await state.set_state(OrderForm.what); await m.answer("📦 Что везём?")

@dp.message(OrderForm.what)
async def order_what(m: Message, state: FSMContext):
    await state.update_data(what=m.text); await state.set_state(OrderForm.note); await m.answer("📝 Уточнение? (этаж, кому) или -")

@dp.message(OrderForm.note)
async def order_note(m: Message, state: FSMContext):
    await state.update_data(note=m.text); await state.set_state(OrderForm.price); await m.answer("💰 Цена?")

@dp.message(OrderForm.price)
async def order_price(m: Message, state: FSMContext):
    data=await state.get_data()
    from_addr=data.get("from_addr"); to_addr=data.get("to_addr"); what=data.get("what"); note=data.get("note")
    price=m.text.replace("тг","").strip()
    init_db()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT INTO orders (client_id, client_username, address_from, address_to, what, note, price) VALUES (?,?,?,?,?,?,?)", (m.from_user.id, m.from_user.username, from_addr, to_addr, what, note, price))
    order_id=c.lastrowid
    c.execute("SELECT user_id FROM couriers"); couriers=c.fetchall()
    conn.commit(); conn.close()
    await state.clear()
    await m.answer(f"✅ Заказ #{order_id} принят! {from_addr}->{to_addr} {what} {price}тг", reply_markup=client_kb())
    await m.answer("Связь:", reply_markup=contact_kb())
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Взять за {price}тг", callback_data=f"take_{order_id}")]])
    text_c=f"🔥 ЗАКАЗ #{order_id}\nОт: {from_addr}\nДо: {to_addr}\nЧто: {what}\nУточнение: {note}\nЦена: {price}тг\nКлиент: @{m.from_user.username}"
    for (cid,) in couriers:
        try: await bot.send_message(cid, text_c, reply_markup=kb)
        except Exception as e: print(f"Не отправил {cid}: {e}")

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cq: CallbackQuery):
    order_id=int(cq.data.split("_")[1])
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT status, client_id, address_from, address_to, what, note, price FROM orders WHERE id=?", (order_id,))
    row=c.fetchone()
    if not row: await cq.answer("Не найден"); conn.close(); return
    status,client_id,from_addr,to_addr,what,note,price=row
    if status!='new': await cq.answer("Уже взяли!", show_alert=True); conn.close(); return
    c.execute("UPDATE orders SET status='taken', courier_id=? WHERE id=?", (cq.from_user.id, order_id)); conn.commit(); conn.close()
    from_q=urllib.parse.quote(f"{from_addr}, Павлодар"); to_q=urllib.parse.quote(f"{to_addr}, Павлодар")
    yandex_url=f"https://yandex.kz/maps/?rtext={from_q}~{to_q}&rtt=auto"
    google_url=f"https://www.google.com/maps/dir/?api=1&origin={from_q}&destination={to_q}"
    kb_route=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚕 Яндекс Маршрут", url=yandex_url)],[InlineKeyboardButton(text="📍 Google", url=google_url)],[InlineKeyboardButton(text="📞 Клиент", url=f"tg://user?id={client_id}")]])
    await cq.message.edit_text(f"ТЫ ВЗЯЛ #{order_id} {price}тг\n{from_addr}->{to_addr}\n{what} / {note}", reply_markup=kb_route)
    await cq.message.answer("Жми Обновить где я, в конце Я доставил", reply_markup=courier_kb())
    await cq.answer("Взял!")
    try:
        kb_client=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛵 Курьер", url=f"tel:{COURIER_MAIN_PHONE}")],[InlineKeyboardButton(text="📞 Оператор", url=f"tel:{OPERATOR_PHONE}")]])
        await bot.send_message(client_id, f"✅ Заказ #{order_id} взял курьер @{cq.from_user.username}", reply_markup=kb_client)
    except: pass

@dp.message(F.location)
async def handle_loc(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,)); row=c.fetchone(); conn.close()
    if not row: return
    order_id,client_id=row
    try: await bot.send_message(client_id, f"🚚 Курьер едет #{order_id}:"); await bot.send_location(client_id, latitude=m.location.latitude, longitude=m.location.longitude); await m.answer("📍 Отправил!")
    except: pass

@dp.message(F.text=="✅ Я доставил - фотоотчет")
async def ask_photo(m: Message, state: FSMContext):
    await state.set_state(PhotoReport.waiting_photo); await m.answer("Скинь фото у двери")

@dp.message(PhotoReport.waiting_photo, F.photo)
async def handle_photo_report(m: Message, state: FSMContext):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id, client_id, price FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,)); row=c.fetchone()
    if not row: await m.answer("Нет активного"); await state.clear(); conn.close(); return
    order_id,client_id,price=row
    c.execute("UPDATE orders SET status='done' WHERE id=?", (order_id,)); conn.commit(); conn.close()
    await state.clear()
    total,cnt=get_earnings(m.from_user.id)
    try: await bot.send_message(client_id, f"✅ Заказ #{order_id} доставлен!"); await bot.send_photo(client_id, m.photo[-1].file_id, caption=f"Фотоотчет #{order_id}")
    except: pass
    await m.answer(f"Закрыт #{order_id}! Заработок: {total}тг ({cnt})", reply_markup=courier_kb())

@dp.message(F.photo)
async def auto_photo(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,)); row=c.fetchone(); conn.close()
    if row:
        order_id,client_id=row
        try: await bot.send_photo(client_id, m.photo[-1].file_id); await m.answer("Фото отправил!")
        except: pass

@dp.message(Command("orders"))
async def list_orders(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT id, address_from, address_to, what, price, status FROM orders ORDER BY id DESC LIMIT 10"); rows=c.fetchall(); conn.close()
    await m.answer("\n".join([f"#{o} {f}->{t} {w} {p}[{s}]" for o,f,t,w,p,s in rows]) if rows else "Нет заказов")

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
async def run_bot():
    init_db(); await dp.start_polling(bot)
if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())
    
