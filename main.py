# bot: @hse_tinkoff_investments_bot
import requests
import json
import datetime
import urllib
import telebot
from telebot import types
import sqlite3
import pandas as pd
import mplfinance as fplt

TINK_TOKEN = "t.qBk_7izffGaLoKNHn-YfFMReJ-gHG0u5Vn0iXSutg2Q4HeOGg_T02Hk0xWTQl3RY3CM0zAlQ4jdgLfwDhjcQ1Q"
BASE_URL = 'https://api-invest.tinkoff.ru/openapi/sandbox/'
BOT_TOKEN = '1859818003:AAHk6ltfnooJ-PqqqbHa-iGq6d3RKUrpBzM'

def do_request(url, token=TINK_TOKEN, method='GET', params={}, data=""):
    url = url + '?' + urllib.parse.urlencode(params)
    if method == "GET":
        return requests.get(BASE_URL + url, data=data,
                     headers={'Authorization' : f"Bearer {token}"})
    elif method == "POST":
        return requests.post(BASE_URL + url, data=data,
                     headers={'Authorization' : f"Bearer {token}"})
    else:
        return None
    
conn = sqlite3.connect('user_tokens.db')
cursor = conn.cursor()
try:
    query = 'CREATE TABLE "tokens" ("ID" INTEGER UNIQUE, "user_id" INTEGER, "token" TEXT, PRIMARY KEY ("ID"))'
    cursor.execute(query)
except:
    pass

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(func=lambda msg: msg.text=='Ввести токен')
def update_token(message):
    message = bot.send_message(message.from_user.id, text='Отправь мне токен без пробелов и переносов строки, чистый токен')
    bot.register_next_step_handler(message, add_token)

def add_token(message):
    with sqlite3.connect('user_tokens.db') as con:
        print(message.text)
        resp = do_request('/sandbox/register', message.text, 'POST', data=json.dumps({'brokerAccountType':'Tinkoff'}))
        if resp.status_code != 200:
            try_again(message, update_token)
            return
        cursor = con.cursor()
        cursor.execute(f"DELETE FROM tokens WHERE user_id = '{message.from_user.id}'")
        con.commit()
        cursor.execute('INSERT INTO tokens (user_id, token) VALUES (?, ?)', (message.from_user.id, message.text))
        con.commit()
    bot.send_message(message.chat.id, 'Готово!')

def try_again(message, operation, problem_info=''):
    itembtn1 = types.KeyboardButton('Да')
    itembtn2 = types.KeyboardButton('Нет')
    keyboard = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True, resize_keyboard=True)
    keyboard.add(itembtn1, itembtn2)
    new_message = bot.send_message(message.chat.id, f'Похоже что то пошло не так :(\n{problem_info}\nПопробуем еще раз?', reply_markup=keyboard)
    bot.register_next_step_handler(new_message, lambda msg: yesno(msg, operation))
    
def yesno(message, operation):
    if message.text == "Да":
        operation(message)
    else:
        send_keyboard(message)
        
def get_token(used_id):
    with sqlite3.connect('user_tokens.db') as con:
        cursor = con.cursor()
        cursor.execute(f"SELECT token FROM tokens WHERE user_id={used_id}")
        token = cursor.fetchone()
        if token is None:
            return TINK_TOKEN
        return token[0]

def get_portfolio(message):
    token = get_token(message.from_user.id)
    resp = do_request('/portfolio/currencies', token=token)
    currencies = resp.json()
    resp = do_request('/portfolio', token=token)
    portfolio = resp.json()
    text = ''
    for i, position in enumerate(currencies['payload']['currencies']):
        text += f"{i+1}) {position['currency']}" + '\n' + f"Баланс: {position['balance']}" + '\n'
    for i, position in enumerate(portfolio['payload']['positions']):
        if position['name'] in ['Доллар США', 'Евро']: continue
        text += f"{i+4}) {position['name']}" + '\n' + f"Тикер: {position['ticker']}" + '\n' + \
            f"Тип инструмента: {position['instrumentType']}" + '\n' + f"Количество лотов: {position['lots']}" + '\n'
    bot.send_message(message.from_user.id, text=text)
    send_keyboard(message)
        
def update_balance(message):
    btns = [types.KeyboardButton('RUB'), types.KeyboardButton('USD'), types.KeyboardButton('EUR')]
    keyboard = types.ReplyKeyboardMarkup(row_width=3, one_time_keyboard=True, resize_keyboard=True)
    keyboard.add(*btns)
    msg = bot.send_message(message.from_user.id, text="Выберите валюту пополнения", reply_markup=keyboard)
    bot.register_next_step_handler(msg, get_currency)

def get_currency(message):
    if message.text not in ['USD', 'RUB', 'EUR']:
        try_again(message, update_balance)
    else:
        msg = bot.send_message(message.from_user.id, text="Введите положительное число - сумму пополнения")
        bot.register_next_step_handler(msg, lambda msg: get_amount(msg, message.text))
    
def get_amount(message, currency):
    try:
        value = int(message.text)
        if value > 0:
            token = get_token(message.from_user.id)
            resp = do_request('/portfolio/currencies', token=token)
            currencies = resp.json()['payload']['currencies']
            payload = list(filter(lambda d: d['currency'] == currency, currencies))[0]
            payload['balance'] += value
            resp = do_request('/sandbox/currencies/balance', method='POST', token=token, data=json.dumps(payload))
            bot.send_message(message.from_user.id, text='Готово!')
            send_keyboard(message)
        else:
            try_again(message, update_balance)
    except:
        try_again(message, update_balance)

def print_instruments(message):
    btns = [types.KeyboardButton('Акции'), types.KeyboardButton('Облигации'), types.KeyboardButton('Фонды')]
    keyboard = types.ReplyKeyboardMarkup(row_width=3, one_time_keyboard=True, resize_keyboard=True)
    keyboard.add(*btns)
    msg = bot.send_message(message.from_user.id, text="Выберите тип инструмента, который вам нужен", reply_markup=keyboard)
    bot.register_next_step_handler(msg, get_type)
    
def get_type(message):
    if message.text not in ['Акции', 'Облигации', 'Фонды']:
        try_again(message, print_instruments)
    else:
        translate = {'Акции': 'stocks', 'Облигации': 'bonds', 'Фонды': 'etfs'}
        token = get_token(message.from_user.id)
        resp = do_request(f'/market/{translate[message.text]}', token=token)
        text = ''
        instruments = resp.json()['payload']['instruments']
        last = 0
        i = 0
        while i != len(instruments):
            item = instruments[i]
            s = f"{i+1}) {item['name']}\nТикер: {item['ticker']}" + '\n'
            if len(text) + len(s) > 4096:
                bot.send_message(message.from_user.id, text=text)
                text = ''
            text += s
            i += 1
        bot.send_message(message.from_user.id, text=text)
        send_keyboard(message)

def buy_instrument(message):
    msg = bot.send_message(message.from_user.id, text="Введите количество лотов, которое вы хотите купить.\
                                                       В песочнице все инструменты стоят 100 единиц валюты, валюта зависит от самого инструмента.")
    bot.register_next_step_handler(msg, lambda msg: get_lots(msg, 'Buy'), buy_instrument)
    
def sell_instrument(message):
    msg = bot.send_message(message.from_user.id, text="Введите количество лотов, которое вы хотите продать.\
                                                       В песочнице все инструменты стоят 100 единиц валюты, валюта зависит от самого инструмента.\
                                                       Не забудьте, что вы не можете продать акций больше чем у вас есть.")
    bot.register_next_step_handler(msg, lambda msg: get_lots(msg, 'Sell'), sell_instrument)

def get_lots(message, operation, retry):
    try:
        value = int(message.text)
        if value > 0:
            msg = bot.send_message(message.from_user.id, text="Введите тикер инструмента.")
            bot.register_next_step_handler(msg, lambda msg: get_ticker(msg, operation, value, retry))
        else:
            try_again(message, retry)
    except:
        try_again(message, retry)
    
def get_ticker(message, operation, lots_count, retry):
    token = get_token(message.from_user.id)
    resp = do_request('/market/search/by-ticker', token=token, params={'ticker':message.text})
    if resp.status_code!= 200 or resp.json()['payload']['total'] == 0:
        try_again(message, retry)
    else:
        figi = resp.json()['payload']['instruments'][0]['figi']
        resp = do_request('/orders/market-order',token=token, method='POST',
                          params={'figi':figi}, data=json.dumps({'lots':lots_count, 'operation':operation}))
        if resp.status_code == 200:
            bot.send_message(message.from_user.id, text='Готово!')
            send_keyboard(message)
        else:
            try_again(message, retry, 'Проверьте, что у вас достаточно денег для покупки/лотов для продажи')
            
def get_instrument_info(message):
    msg = bot.send_message(message.from_user.id, text="Введите тикер инструмента.")
    bot.register_next_step_handler(msg, show_info)
    
def show_info(message):
    token = get_token(message.from_user.id)
    info_resp = do_request('/market/search/by-ticker', token=token, params={'ticker':message.text})
    if info_resp.status_code!= 200 or info_resp.json()['payload']['total'] == 0:
        try_again(message, get_instrument_info)
    else:
        info = info_resp.json()['payload']['instruments'][0]
        resp = do_request('/market/orderbook', token=token, params={'figi':info['figi'],'depth':10})
        orderbook = resp.json()['payload']
        nl='\n'
        text = f'''{info["name"]}:
Статус: {orderbook["tradeStatus"]}
Валюта: {info['currency']}
Шаг цены: {orderbook["minPriceIncrement"]}
Рыночная цена: {orderbook["lastPrice"]}
Стакан: Продажа
{"".join(list(map(lambda d: f"Цена: {d['price']}, Количество: {d['quantity']}{nl}", orderbook["asks"][::-1])))}Стакан: Покупка
{"".join(list(map(lambda d: f"Цена: {d['price']}, Количество: {d['quantity']}{nl}", orderbook["bids"])))}
'''
        bot.send_message(message.from_user.id, text=text)
        send_keyboard(message)
        
def send_chart(message):
    msg = bot.send_message(message.from_user.id, text="Введите тикер инструмента.")
    bot.register_next_step_handler(msg, get_chart_ticker)

def get_chart_ticker(message):
    token = get_token(message.from_user.id)
    info_resp = do_request('/market/search/by-ticker', token=token, params={'ticker':message.text})
    if info_resp.status_code!= 200 or info_resp.json()['payload']['total'] == 0:
        try_again(message, send_chart)
    else:
        info = info_resp.json()['payload']['instruments'][0]
        msg = bot.send_message(message.from_user.id, text="Введите интервал одной свечи. Доступные варианты:\
                                                           1min, 2min, 3min, 5min, 10min, 15min, 30min, hour, day, week, month")
        bot.register_next_step_handler(msg, lambda msg: get_interval(msg, info))
    
def get_interval(message, info):
    intervals = ['1min', '2min', '3min', '5min', '10min', '15min', '30min', 'hour', 'day', 'week', 'month']
    time_delta= dict([(f'{k}min', datetime.timedelta(minutes=k)) for k in [1,2,3,5,10,15,30]] + \
                [('hour', datetime.timedelta(hours=1)), ('day', datetime.timedelta(days=1)),
                ('week', datetime.timedelta(days=7)), ('month', datetime.timedelta(days=30))])
    print(time_delta)
    if message.text not in intervals:
        try_again(message, send_chart)
    else:
        to_d = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=3)))
        if message.text not in ['15min', '30min']:
            from_d = to_d - 100*time_delta[message.text]
        elif message.text == '15min':
            from_d = to_d - 60*time_delta[message.text]
        else:
            from_d = to_d - 47*time_delta[message.text]
        resp = do_request('/market/candles', params={'figi':info['figi'],'from':from_d.isoformat(),
                                                     'to':to_d.isoformat(), 'interval':message.text})
        print(resp.json())
        candles = resp.json()['payload']['candles']
        if len(candles) == 0:
            bot.send_message(message.from_user.id, text="Извините, в это время биржа была закрыта, попробуйте выбрать больший временной промежуток")
            try_again(message, send_chart)
            return
        df = pd.DataFrame(candles)
        df.columns = ['Open', 'Close', 'High', 'Low', 'Value', 'time', 'interval', 'figi']
        df.index = pd.DatetimeIndex(df['time'])
        fplt.plot(df, type='candle', style='charles', title=info['name'], ylabel='Price',
                  savefig='candle_chart.png', figratio=(11,6))
        with open('candle_chart.png', 'rb') as img:
            bot.send_photo(message.chat.id, photo=img,
                           caption=f'График цены акции {info["name"]}, цена в {info["currency"]}.\n\
Изменение цены за весь период: {(float(df.tail(1)["Close"]) - float(df.head(1)["Open"])) / (float(df.head(1)["Open"])) * 100}%')
        send_keyboard(message)
        
@bot.message_handler(commands=['start', 'help'])
def say_hello(message):
    with sqlite3.connect('user_tokens.db') as con:
        cursor = con.cursor()
        cursor.execute(f"SELECT user_id FROM tokens WHERE user_id={message.from_user.id}")
        data = cursor.fetchall()
        if len(data):
            itembtn1 = types.KeyboardButton('Обновить токен')
            itembtn2 = types.KeyboardButton('Продолжить')
            ending = 'Продолжить с тем же токеном?'
        else:
            itembtn1 = types.KeyboardButton('Ввести токен')
            itembtn2 = types.KeyboardButton('Продолжить без токена')
            ending = 'Хочешь ввести свой токен, или продолжить со стандартным?'
    text = '''Привет! Я - бот, который позволит тебе работать с Тинькофф Инвестициями в Telegram.
Все действия исполняются в т.н. "песочнице", реальных покупок/пополнений не происходит.
Ты можешь получить свой собственный токен песочницы и работать с индивидуальным счетом, или просто попробовать на стандартном, но другие люди тоже могут пользоваться этим счетом.
Как получить свой токен описано здесь: https://tinkoffcreditsystems.github.io/invest-openapi/auth/
''' + ending
    keyboard = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True, resize_keyboard=True)
    keyboard.add(itembtn1, itembtn2) # добавим кнопки 1 и 2 на первый ряд
    msg = bot.send_message(message.from_user.id, text=text, reply_markup=keyboard)

@bot.message_handler(func=lambda msg: True)
def send_keyboard(message):
    buttons = [types.KeyboardButton('Посмотреть портфель'), types.KeyboardButton('Пополнить счет'), types.KeyboardButton('Купить'),
               types.KeyboardButton('Продать'), types.KeyboardButton('Посмотреть список инструментов'),
               types.KeyboardButton('Посмотреть информацию об инструменте'), types.KeyboardButton('Посмотреть график'),
               types.KeyboardButton('Вернуться в начало')]
    keyboard = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    keyboard.add(*buttons)
    bot.send_message(message.from_user.id, text="Что вы хотите сделать?", reply_markup=keyboard)
    bot.register_next_step_handler(message, callback_worker)
    
def callback_worker(message):
    if message.text == "Посмотреть портфель":
        get_portfolio(message)
    elif message.text == "Пополнить счет":
        update_balance(message)
    elif message.text == "Купить":
        buy_instrument(message)
    elif message.text == "Продать":
        sell_instrument(message)
    elif message.text == "Посмотреть список инструментов":
        print_instruments(message)
    elif message.text == "Посмотреть информацию об инструменте":
        get_instrument_info(message)
    elif message.text == "Посмотреть график":
        send_chart(message)
    elif message.text == "Вернуться в начало":
        say_hello(message)
        return
    else:
        bot.send_message(message.from_user.id, text="Я не понимаю :(")
        send_keyboard(message)

while True:
    try:
        bot.polling(none_stop=True)
    except KeyboardInterrupt:
        break
    except SystemExit:
        break
    else:
        pass
