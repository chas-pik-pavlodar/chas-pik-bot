import os, logging, threading, asyncio, sqlite3, urllib.parse, requests
from flask import Flask
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.environ.get("TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1218877896"))
DB = "database.db"

OPERATOR_PHONE = "+77771234567"
COURIER_PHONE = "+77771234567"
MAIN_COURIER_ID = 7714431728

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
@app.route('/')
def home(): return "Bot alive!"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, client_username TEXT, client_name TEXT, address_from TEXT, address_to TEXT, what TEXT, note TEXT, price TEXT, status TEXT DEFAULT 'new', courier_id INTEGER, courier_username TEXT, courier_name TEXT, created DATE DEFAULT CURRENT_DATE, created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS couriers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, username TEXT, full_name TEXT, phone TEXT, last_lat REAL, last_lon REAL, last_time TIMESTAMP)")
    for col in ["client_name TEXT","courier_username TEXT","courier_name TEXT","created DATE","created_time TIMESTAMP","what TEXT","note TEXT","full_name TEXT","last_lat REAL","last_lon REAL","last_time TIMESTAMP"]:
        try:
            table = "couriers" if any(x in col for x in ["full_name","last_lat","last_lon","last_time"]) else "orders"
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
        except: pass
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, full_name, phone) VALUES (?,?,?,?)", (MAIN_COURIER_ID, "main_kurier", "Главный курьер", COURIER_PHONE))
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, full_name, phone) VALUES (?,?,?,?)", (ADMIN_ID, "operator", "Оператор", OPERATOR_PHONE))
    conn.commit(); conn.close()

def get_earnings(courier_id, date_filter=None):
    try:
        conn=sqlite3.connect(DB); c=conn.cursor()
        if date_filter == "today":
            c.execute("SELECT price FROM orders WHERE courier_id=? AND status='done' AND date(created_time)=date('now','localtime')", (courier_id,))
        elif date_filter == "yesterday":
            c.execute("SELECT price FROM orders WHERE courier_id=? AND status='done' AND date(created_time)=date('now','-1 day','localtime')", (courier_id,))
        else:
            c.execute("SELECT price FROM orders WHERE courier_id=? AND status='done'", (courier_id,))
        total=0; rows=c.fetchall()
        for (p,) in rows:
            try: total+=int(''.join(filter(str.isdigit, str(p))) or 0)
            except: pass
        conn.close()
        return total, len(rows)
    except: return 0,0

def get_all_earnings_today():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT courier_id, courier_username, courier_name, price FROM orders WHERE status='done' AND date(created_time)=date('now','localtime')")
    rows=c.fetchall(); conn.close()
    return rows

class OrderForm(StatesGroup):
    from_address=State(); to_address=State(); what=State(); note=State(); price=State()
class PhotoReport(StatesGroup):
    waiting_photo=State()

def client_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📦 Сделать заказ")],
        [KeyboardButton(text="🚚 Стать курьером")],
        [KeyboardButton(text="📞 Связаться с оператором"), KeyboardButton(text="🛵 Связаться с курьером")],
        [KeyboardButton(text="💰 Мой заработок")]
    ], resize_keyboard=True)

def courier_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔴 Включить LIVE на 8 часов")],
        [KeyboardButton(text="✅ Я доставил - фотоотчет")],
        [KeyboardButton(text="💰 Мой заработок"), KeyboardButton(text="📊 Сегодня")],
        [KeyboardButton(text="📞 Связаться с оператором")]
    ], resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📦 Сделать заказ")],
        [KeyboardButton(text="👑 Все заказы"), KeyboardButton(text="🔥 Активные")],
        [KeyboardButton(text="👥 Курьеры"), KeyboardButton(text="🗺 Курьеры на карте")],
        [KeyboardButton(text="💰 Заработки"), KeyboardButton(text="📊 Сегодня")],
        [KeyboardButton(text="📅 Вчера"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🆔 Мой ID")]
    ], resize_keyboard=True)

def format_client(cun, cname, cid):
    if cun and cun!='None': return f"@{cun} ({cname})"
    return cname or f"Клиент {cid}"

def format_courier(cid, cun, cname):
    if not cid: return "не взят"
    if cun and cun!='None': return f"@{cun} {cname or ''}".strip()
    return cname or f"Курьер {cid}"

@dp.message(Command("id"))
@dp.message(Command("whoami"))
@dp.message(F.text=="🆔 Мой ID")
async def my_id(m: Message):
    is_admin = "ДА 👑 АДМИН" if m.from_user.id == ADMIN_ID else "НЕТ, ты клиент/курьер"
    await m.answer(f"🆔 ТВОЙ ID: {m.from_user.id}\n👤 {m.from_user.first_name} @{m.from_user.username}\nАдмин ID в настройках: {ADMIN_ID}\nТы админ? {is_admin}")

@dp.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear(); init_db()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE couriers SET full_name=?, username=? WHERE user_id=?", (m.from_user.first_name, m.from_user.username, m.from_user.id))
    conn.commit(); conn.close()
    if m.from_user.id == ADMIN_ID:
        await m.answer(f"👑 АДМИН {m.from_user.first_name}\nЧАС ПИК Павлодар", reply_markup=admin_kb())
    else:
        await m.answer("ЧАС ПИК Павлодар ⚡️\nБыстрая доставка по Павлодару", reply_markup=client_kb())

@dp.message(F.text=="🔴 Включить LIVE на 8 часов")
async def ask_live(m: Message):
    await m.answer(
        "🔴 Чтобы включить LIVE на 8 часов:\n\n"
        "1. Нажми Скрепка 📎 внизу\n"
        "2. Геопозиция\n"
        "3. Транслировать мою геопозицию\n"
        "4. Выбери 8 часов\n\n"
        "После этого админ будет видеть тебя в реальном времени без нажатий, как в Яндекс Такси! И клиент будет видеть где ты едешь.",
        reply_markup=courier_kb()
    )

@dp.edited_message(F.location)
@dp.message(F.location)
async def handle_live_loc(m: Message):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE couriers SET last_lat=?, last_lon=?, last_time=CURRENT_TIMESTAMP, full_name=?, username=? WHERE user_id=?",
              (m.location.latitude, m.location.longitude, m.from_user.first_name, m.from_user.username, m.from_user.id))
    if m.location.live_period:
        try:
            await m.answer(f"🔴 LIVE включен на {m.location.live_period//3600}ч! Теперь ты на карте у админа в реальном времени.", reply_markup=courier_kb() if m.from_user.id!=ADMIN_ID else admin_kb())
        except: pass
    c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,))
    row=c.fetchone()
    conn.commit(); conn.close()
    if row:
        oid,cid=row
        try:
            if m.location.live_period:
                await bot.send_message(cid, f"🚚 Курьер {m.from_user.first_name} включил LIVE #{oid}, смотри где едет:")
                await bot.send_location(cid, m.location.latitude, m.location.longitude, live_period=m.location.live_period)
            else:
                await bot.send_message(cid, f"🚚 Курьер {m.from_user.first_name} тут #{oid}:")
                await bot.send_location(cid, m.location.latitude, m.location.longitude)
        except: pass

@dp.message(F.text=="🗺 Курьеры на карте")
async def couriers_map(m: Message):
    if m.from_user.id!= ADMIN_ID: return
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT full_name, username, last_lat, last_lon, last_time FROM couriers WHERE last_lat IS NOT NULL ORDER BY last_time DESC")
    rows=c.fetchall(); conn.close()
    if not rows:
        await m.answer("Нет локаций. Попроси курьеров нажать 🔴 Включить LIVE на 8 часов и поделиться геопозицией")
        return
    points = []
    txt = "🗺 КУРЬЕРЫ LIVE:\n\n"
    for fname, uname, lat, lon, ltime in rows:
        points.append(f"{lon},{lat},pm2rdm")
        name = f"@{uname}" if uname and uname!='None' else fname
        txt += f"📍 {name}\n{lat:.5f},{lon:.5f}\nОбнов: {ltime}\n\n"
        try: await bot.send_location(m.chat.id, lat, lon)
        except: pass
    if points:
        pts = "~".join(points)
        map_url = f"https://static-maps.yandex.ru/1.x/?l=map&pt={pts}&z=13&size=650,450"
        txt += f"Общая карта:\n{map_url}"
    await m.answer(txt)

@dp.message(F.text=="📊 Сегодня")
@dp.message(Command("today"))
async def today_earn(m: Message):
    total_today, cnt_today = get_earnings(m.from_user.id, "today")
    total_yest, _ = get_earnings(m.from_user.id, "yesterday")
    total_all, cnt_all = get_earnings(m.from_user.id)
    await m.answer(f"📊 {m.from_user.first_name}:\n\nСегодня: {cnt_today} зак / {total_today} тг\nВчера: {total_yest} тг\nВсего: {cnt_all} зак / {total_all} тг")

@dp.message(F.text=="📅 Вчера")
async def yesterday_admin(m: Message):
    if m.from_user.id!= ADMIN_ID:
        total,cnt=get_earnings(m.from_user.id, "yesterday")
        await m.answer(f"Вчера: {cnt} зак / {total} тг")
        return
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT courier_id, courier_username, courier_name, price FROM orders WHERE status='done' AND date(created_time)=date('now','-1 day','localtime')")
    rows=c.fetchall(); conn.close()
    if not rows: await m.answer("Вчера заказов не было"); return
    txt="📅 ВЧЕРА:\n\n"
    from collections import defaultdict
    stat=defaultdict(lambda: [0,0,"",""])
    for cid,cun,cname,price in rows:
        try: p=int(''.join(filter(str.isdigit, str(price))) or 0)
        except: p=0
        stat[cid][0]+=p; stat[cid][1]+=1; stat[cid][2]=cun; stat[cid][3]=cname
    total_all=0
    for cid,(earn,cnt,cun,cname) in stat.items():
        total_all+=earn
        display = f"@{cun}" if cun and cun!='None' else cname
        txt+=f"{display}: {cnt} зак = {earn}тг\n"
    txt+=f"\nВсего вчера: {total_all}тг"
    await m.answer(txt)

@dp.message(F.text=="👑 Все заказы")
@dp.message(Command("all"))
async def all_orders(m: Message):
    if m.from_user.id!= ADMIN_ID: return
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id, client_username, client_name, address_from, address_to, what, note, price, status, courier_username, courier_name, created_time FROM orders ORDER BY id DESC LIMIT 20")
    rows=c.fetchall(); conn.close()
    if not rows: await m.answer("Заказов нет"); return
    for r in rows:
        oid, cun, cname, afrom, ato, what, note, price, status, kur_un, kur_name, ctime = r
        what_show = what if what and what!='None' else "не указано"
        note_show = note if note and note!='None' else "-"
        txt=f"📦 ЗАКАЗ #{oid} [{status}]\n🕐 {ctime}\n👤 {format_client(cun,cname,'')}\n📍 От: {afrom}\n🏁 До: {ato}\n📦 Что: {what_show}\n📝 Уточн: {note_show}\n💰 {price}тг\n🛵 Курьер: {format_courier(1,kur_un,kur_name)}"
        await m.answer(txt)

@dp.message(F.text=="🔥 Активные")
async def active_orders(m: Message):
    if m.from_user.id!= ADMIN_ID: return
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id, client_username, client_name, address_from, address_to, what, price, courier_username, courier_name FROM orders WHERE status='taken' ORDER BY id DESC")
    rows=c.fetchall(); conn.close()
    if not rows: await m.answer("Активных нет"); return
    txt="🔥 В ДОСТАВКЕ:\n\n"
    for r in rows:
        txt+=f"#{r[0]} {format_client(r[1],r[2],'')} 📦{r[5]} {r[3]}->{r[4]} {r[6]}тг Курьер {format_courier(1,r[7],r[8])}\n\n"
    await m.answer(txt)

@dp.message(F.text=="👥 Курьеры")
@dp.message(Command("couriers"))
async def list_c(m: Message):
    init_db()
    conn=sqlite3.connect(DB); c=conn.cursor(); c.execute("SELECT user_id, username, full_name, last_time FROM couriers"); rows=c.fetchall(); conn.close()
    txt=f"👥 КУРЬЕРОВ: {len(rows)}\n\n"
    for uid,uname,fname,ltime in rows:
        today,_=get_earnings(uid,"today")
        total,cnt=get_earnings(uid)
        name_str = f"@{uname}" if uname else fname
        live = f"LIVE до {ltime}" if ltime else "нет локации"
        txt+=f"{name_str} ({fname})\n{today}тг сегодня / {total}тг всего ({cnt} зак)\n{live}\n\n"
    await m.answer(txt)

@dp.message(F.text=="💰 Заработки")
@dp.message(Command("earnings"))
async def earn_admin(m: Message):
    if m.from_user.id!= ADMIN_ID: return
    rows=get_all_earnings_today()
    if not rows: await m.answer("Сегодня пока 0 доставок"); return
    from collections import defaultdict
    stat=defaultdict(lambda: [0,0,"",""])
    for cid,cun,cname,price in rows:
        try: p=int(''.join(filter(str.isdigit, str(price))) or 0)
        except: p=0
        stat[cid][0]+=p; stat[cid][1]+=1; stat[cid][2]=cun; stat[cid][3]=cname
    txt=f"💰 СЕГОДНЯ {datetime.now().strftime('%d.%m.%Y')}:\n\n"
    total_all=0
    for cid,(earn,cnt,cun,cname) in stat.items():
        total_all+=earn
        display = f"@{cun}" if cun and cun!='None' else cname
        txt+=f"{display}: {cnt} зак = {earn}тг\n"
    txt+=f"\nВсего сегодня: {total_all}тг"
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT SUM(CAST(price AS INTEGER)) FROM orders WHERE status='done'"); total_all_time=c.fetchone()[0] or 0
    conn.close()
    txt+=f"\nЗа все время: {total_all_time}тг"
    await m.answer(txt)

@dp.message(F.text=="📊 Статистика")
async def stat(m: Message):
    if m.from_user.id!= ADMIN_ID: return
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT COUNT(*), status FROM orders GROUP BY status")
    rows=c.fetchall()
    c.execute("SELECT COUNT(*) FROM orders WHERE date(created_time)=date('now','localtime')"); today=c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders"); total=c.fetchone()[0]
    conn.close()
    txt=f"📊 Статистика:\nВсего: {total}\nСегодня: {today}\n\n"
    for cnt,st in rows: txt+=f"{st}: {cnt}\n"
    await m.answer(txt)

@dp.message(F.text=="📞 Связаться с оператором")
async def contact_op(m: Message): await m.answer(f"📞 Оператор: {OPERATOR_PHONE}")
@dp.message(F.text=="🛵 Связаться с курьером")
async def contact_kur(m: Message): await m.answer(f"🛵 Курьер: {COURIER_PHONE}")
@dp.message(F.text=="🚚 Стать курьером")
async def become(m: Message):
    init_db()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO couriers (user_id, username, full_name, phone) VALUES (?,?,?,?)", (m.from_user.id, m.from_user.username, m.from_user.first_name, COURIER_PHONE))
    c.execute("UPDATE couriers SET full_name=?, username=? WHERE user_id=?", (m.from_user.first_name, m.from_user.username, m.from_user.id))
    conn.commit(); conn.close()
    await m.answer(f"✅ Ты курьер {m.from_user.first_name}!", reply_markup=courier_kb() if m.from_user.id!=ADMIN_ID else admin_kb())

@dp.message(F.text=="💰 Мой заработок")
async def my_earn(m: Message):
    today,cnt_today=get_earnings(m.from_user.id,"today")
    total,cnt_all=get_earnings(m.from_user.id)
    yesterday,_=get_earnings(m.from_user.id,"yesterday")
    await m.answer(f"💰 {m.from_user.first_name}:\nСегодня: {cnt_today} зак / {today} тг\nВчера: {yesterday} тг\nВсего: {cnt_all} зак / {total} тг\n\nЗавтра начнется с 0.")

@dp.message(F.text=="📦 Сделать заказ")
async def order_start(m: Message, state: FSMContext):
    await state.set_state(OrderForm.from_address); await m.answer("📍 Откуда забрать?")

@dp.message(OrderForm.from_address)
async def order_from(m: Message, state: FSMContext):
    await state.update_data(from_addr=m.text); await state.set_state(OrderForm.to_address); await m.answer("🏁 Куда доставить?")

@dp.message(OrderForm.to_address)
async def order_to(m: Message, state: FSMContext):
    await state.update_data(to_addr=m.text); await state.set_state(OrderForm.what); await m.answer("📦 Что везём? (например фурнитура)")

@dp.message(OrderForm.what)
async def order_what(m: Message, state: FSMContext):
    await state.update_data(what=m.text); await state.set_state(OrderForm.note); await m.answer("📝 Уточнение? или -")

@dp.message(OrderForm.note)
async def order_note(m: Message, state: FSMContext):
    await state.update_data(note=m.text); await state.set_state(OrderForm.price); await m.answer("💰 Цена?")

@dp.message(OrderForm.price)
async def order_price(m: Message, state: FSMContext):
    data=await state.get_data()
    from_addr=data.get("from_addr"); to_addr=data.get("to_addr"); what=data.get("what"); note=data.get("note")
    price=m.text.replace("тг","").strip()
    client_name = m.from_user.first_name or "Клиент"
    client_username = m.from_user.username
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT INTO orders (client_id, client_username, client_name, address_from, address_to, what, note, price, created_time) VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)", (m.from_user.id, client_username, client_name, from_addr, to_addr, what, note, price))
    order_id=c.lastrowid
    c.execute("SELECT user_id FROM couriers"); couriers=c.fetchall()
    conn.commit(); conn.close()
    await state.clear()
    kb_menu = admin_kb() if m.from_user.id==ADMIN_ID else client_kb()
    await m.answer(f"✅ Заказ #{order_id} принят!\n\nОт: {from_addr}\nДо: {to_addr}\nЧто: {what}\nЦена: {price}тг\n\nИщем курьера...", reply_markup=kb_menu)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Взять за {price}тг", callback_data=f"take_{order_id}")]])
    text=(f"🔥 ЗАКАЗ #{order_id}\nКлиент: {format_client(client_username, client_name, '')}\nОт: {from_addr}\nДо: {to_addr}\n📦 Что: {what}\n📝 {note}\nЦена: {price}тг")
    sent=0
    for (cid,) in couriers:
        try:
            await bot.send_message(cid, text, reply_markup=kb)
            sent+=1
        except: pass
    if m.from_user.id!= ADMIN_ID:
        try: await bot.send_message(ADMIN_ID, f"👑 НОВЫЙ #{order_id}\n{text}\nРазослан {sent} курьерам")
        except: pass

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cq: CallbackQuery):
    order_id=int(cq.data.split("_")[1])
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT status, client_id FROM orders WHERE id=?", (order_id,))
    row=c.fetchone()
    if not row: await cq.answer("Не найден"); conn.close(); return
    status,client_id=row
    if status!='new': await cq.answer("Уже взяли!"); conn.close(); return
    c.execute("UPDATE orders SET status='taken', courier_id=?, courier_username=?, courier_name=? WHERE id=?", (cq.from_user.id, cq.from_user.username, cq.from_user.first_name, order_id)); conn.commit(); conn.close()
    await cq.message.edit_text(f"ТЫ ВЗЯЛ #{order_id} - включи LIVE!")
    await cq.answer("Взял!")
    try: await bot.send_message(client_id, f"✅ Заказ #{order_id} взял {cq.from_user.first_name} Тел: {COURIER_PHONE}\nКурьер включит LIVE и ты увидишь где едет")
    except: pass

@dp.message(F.text=="✅ Я доставил - фотоотчет")
async def ask_photo(m: Message, state: FSMContext):
    await state.set_state(PhotoReport.waiting_photo); await m.answer("Скинь фото доставки")

@dp.message(PhotoReport.waiting_photo, F.photo)
async def handle_photo(m: Message, state: FSMContext):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,)); row=c.fetchone()
    if not row: await state.clear(); conn.close(); return
    oid,cid=row
    c.execute("UPDATE orders SET status='done' WHERE id=?", (oid,)); conn.commit(); conn.close()
    await state.clear()
    today,_=get_earnings(m.from_user.id,"today")
    total,_=get_earnings(m.from_user.id)
    await m.answer(f"✅ Закрыт #{oid}!\nСегодня: {today}тг\nВсего: {total}тг", reply_markup=admin_kb() if m.from_user.id==ADMIN_ID else courier_kb())
    try: await bot.send_message(cid, f"✅ Заказ #{oid} доставлен! Фото у курьера")
    except: pass

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
async def run_bot():
    init_db(); await dp.start_polling(bot)
if __name__=="__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())
