#... вставь предыдущий код до функции take_order, а саму take_order замени на эту версию...

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cq: CallbackQuery):
    order_id = int(cq.data.split("_")[1])
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT status, client_id, address_from, address_to, price FROM orders WHERE id=?", (order_id,))
    row = c.fetchone()
    if not row:
        await cq.answer("Не найден"); conn.close(); return
    status, client_id, from_addr, to_addr, price = row
    if status!= 'new':
        await cq.answer("Уже взяли!", show_alert=True); conn.close(); return
    c.execute("UPDATE orders SET status='taken', courier_id=? WHERE id=?", (cq.from_user.id, order_id))
    conn.commit(); conn.close()

    # Кнопки маршрута для курьера
    import urllib.parse
    from_enc = urllib.parse.quote(from_addr)
    to_enc = urllib.parse.quote(to_addr)
    gis_url = f"https://2gis.kz/pavlodar/search/{from_enc} to {to_enc}"
    google_url = f"https://www.google.com/maps/dir/?api=1&origin={from_enc}&destination={to_enc}"

    kb_route = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Маршрут 2GIS (для Павлодара)", url=gis_url)],
        [InlineKeyboardButton(text="📍 Маршрут Google Maps", url=google_url)]
    ])
    kb_share = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 Я выехал - показать где я", request_location=True)]], resize_keyboard=True)

    await cq.message.edit_text(f"ТЫ ВЗЯЛ ЗАКАЗ #{order_id} за {price}\nОт: {from_addr}\nДо: {to_addr}", reply_markup=kb_route)
    await cq.message.answer("Нажми чтобы клиент видел где ты едешь:", reply_markup=kb_share)
    await cq.answer("Твой!")

    try:
        await bot.send_message(client_id, f"✅ Твой заказ #{order_id} взял курьер @{cq.from_user.username} за {price}\nСкоро он поделится местоположением и ты увидишь где он едет.")
    except: pass

@dp.message(F.location)
async def handle_location(m: Message):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, client_id FROM orders WHERE courier_id=? AND status='taken' ORDER BY id DESC LIMIT 1", (m.from_user.id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return
    order_id, client_id = row
    try:
        await bot.send_message(client_id, f"🚚 Курьер с заказом #{order_id} едет! Вот где он сейчас:")
        await bot.send_location(client_id, latitude=m.location.latitude, longitude=m.location.longitude)
        await m.answer("Отправил клиенту твое местоположение! Можешь отправлять еще по ходу движения.")
    except:
        pass
