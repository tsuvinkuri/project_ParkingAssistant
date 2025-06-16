import telebot
import subprocess
import requests
from telebot import types
from urllib.parse import quote
from signs_data import signs_info
from signs_data_full import full_signs_info
from dotenv import load_dotenv
import os

load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)
photo_number = 0
waiting_for_photo = False
show_sign_information = False


# будущая возможность
def get_location_info(lat, lon):
    url = "https://geocode-maps.yandex.ru/1.x/"
    params = {
        'format': 'json',
        'geocode': f'{lon},{lat}',
        'kind': 'locality',
        'results': 1
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()
        feature = data['response']['GeoObjectCollection']['featureMember'][0]
        return feature['GeoObject']['name']
    except Exception as e:
        return None


def generate_parking_search_link(lat, lon, city=None):
    if city:
        search_query = quote(f"Парковка в {city}")
    else:
        search_query = quote("Парковка")
    return f"https://yandex.ru/maps/?mode=search&text={search_query}&ll={lon},{lat}&z=14"


# генерация ответа пользователю
def generate_response(all_signs):
    all_signs = process_detected_signs(all_signs)
    all_signs = [sign for sign in all_signs if sign in signs_info]
    all_signs = set(all_signs)
    if len(all_signs) == 0:
        return "Не было распознано каких-либо дорожных знаков. " \
               "Пожалуйста, попробуйте загрузить фотографию более высокого качества или поменять ракурс."
    detected_signs = ' '.join(all_signs).replace(' ', ', ')
    response = f"Распознанные знаки: {detected_signs}\n"
    forbidden_signs = [sign for sign in all_signs if sign.startswith("3_")]
    all_signs = process_detected_signs(all_signs)
    if "3_27" in forbidden_signs:
        response += "Остановка и стоянка запрещены (знак 3_27)\n"
        if "8_5_1" in all_signs:
            response += "Остановка запрещена только в субботу, воскресенье и праздничные дни.\n"
        if "8_5_2" in all_signs:
            response += "Остановка запрещена только в рабочие дни.\n"
        if "8_5_3" in all_signs:
            response += "Остановка запрещена только в указанные на знаки дни недели.\n"
        if "8_5_4" in all_signs:
            response += "Остановка запрещена только в промежуток времени, указанный на знаке.\n"
        response += "Риск эвакуации: Очень высокий\n"
        all_signs.remove('3_27')
        forbidden_signs.remove('3_27')
        if len([sign for sign in all_signs if sign.startswith("8_")]) == 0:
            response += "Это - приоритетный знак, и не было распознано других знаков, разрешающих дальнейшую парковку."
            return response
    for sign in forbidden_signs:
        if sign in signs_info:
            info = signs_info[sign]
            response += (
                f"{info['name']} ({sign})\n"
                f"- Парковка: {info['parking']}\n"
                f"- Время: {info['time']}\n"
                f"- Риск эвакуации: {info['evacuation_risk']}\n"
            )
    plates = [sign for sign in all_signs if sign.startswith("8_")]
    if plates:
        response += "\nДополнительные условия:\n"
        for plate in plates:
            if plate in signs_info:
                info = signs_info[plate]
                response += f"- {info['name']}: {info['description']}\n"
    allowed_signs = [sign for sign in all_signs if sign in ["6_4", "5_29", "6_4s"]]
    if allowed_signs and not forbidden_signs:
        response += "\nМожно парковаться (если соблюдены условия)\n"
    return response


# обработка обобщающих знаков к одному виду (8.6.x -> 8.6, 8.4.x -> 8.4 и т.п)
def process_detected_signs(all_signs):
    normalized_signs = []
    for sign in all_signs:
        parts = sign.split('_')
        if len(parts) == 3 and parts[0] == '8' and (parts[1] == '6' or parts[1] == '4' or (parts[1] == '1' and (parts[2] == '3' or parts[2] == '4'))):
            normalized_signs.append(f"{parts[0]}_{parts[1]}")
        else:
            normalized_signs.append(sign)
    return normalized_signs


# проверка того, что пользователь отправил сообщение, которое есть в кнопках
def check_correct_answer(user_answer, button_answers):
    if user_answer in button_answers:
        return True
    return False


@bot.message_handler(commands=['start'])
def start(message):
    global deep_level
    deep_level = 0
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("Покажи мне список своих команд")
    markup.add(btn1)
    bot.send_message(message.chat.id, text="Привет, чем могу помочь?", reply_markup=markup)
    deep_level += 1


@bot.message_handler(content_types=['text'])
def func(message):
    global waiting_for_photo
    global show_sign_information
    global deep_level
    if deep_level == 1:
        if check_correct_answer(message.text, ['Покажи мне список своих команд']):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            btn1 = types.KeyboardButton("Распознать знаки парковки")
            btn2 = types.KeyboardButton("Посмотреть список всех парковочных знаков")
            btn3 = types.KeyboardButton("Найти ближайшую парковку")
            markup.add(btn1, btn2, btn3)
            bot.send_message(message.chat.id,
                            text="На данный момент я могу помочь распознать знаки парковки по фотографии, показать список всех парковочных знаков и найти ближайшую парковку.\nПожалуйста, выберите, что Вы хотите сделать.", reply_markup=markup)
            deep_level += 1
        else:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            btn1 = types.KeyboardButton("Покажи мне список своих команд")
            markup.add(btn1)
            bot.send_message(message.chat.id, text="Пожалуйста, используйте кнопки.", reply_markup=markup)
    elif deep_level == 2:
        if check_correct_answer(message.text, ['Распознать знаки парковки', "Посмотреть список всех парковочных знаков", "Найти ближайшую парковку"]):
            if message.text == "Распознать знаки парковки":
                waiting_for_photo = True
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                btn1 = types.KeyboardButton("Вернуться назад")
                markup.add(btn1)
                bot.send_message(message.chat.id, text="Пожалуйста, загрузите фотографии, на которых Вы бы хотели распознать знаки.", reply_markup=markup)
                deep_level += 1
            elif message.text == "Посмотреть список всех парковочных знаков":
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                btn1 = types.KeyboardButton("Вернуться назад")
                markup.add(btn1)
                bot.send_message(message.chat.id,
                                 text="Пожалуйста, укажите номер парковочного знака, информацию про который Вы бы хотели увидеть.",
                                 reply_markup=markup)
                show_sign_information = True
                deep_level += 2
            elif message.text == "Найти ближайшую парковку":
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                btn1 = types.KeyboardButton("Отправить местоположение", request_location=True)
                btn2 = types.KeyboardButton("Вернуться назад")
                markup.add(btn1, btn2)
                bot.send_message(message.chat.id,
                                 text="Пожалуйста, поделитесь своей геопозицией для поиска парковок.",
                                 reply_markup=markup)
        else:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            btn1 = types.KeyboardButton("Распознать знаки парковки")
            btn2 = types.KeyboardButton("Посмотреть список всех парковочных знаков")
            btn3 = types.KeyboardButton("Найти ближайшую парковку")
            markup.add(btn1, btn2, btn3)
            bot.send_message(message.chat.id, text="Пожалуйста, используйте кнопки.", reply_markup=markup)
    elif deep_level == 3:
        if check_correct_answer(message.text, ["Вернуться назад"]):
            deep_level -= 2
            waiting_for_photo = False
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            btn1 = types.KeyboardButton("Распознать знаки парковки")
            btn2 = types.KeyboardButton("Посмотреть список всех парковочных знаков")
            btn3 = types.KeyboardButton("Найти ближайшую парковку")
            markup.add(btn1, btn2, btn3)
            bot.send_message(message.chat.id,
                             text="На данный момент я могу помочь распознать знаки парковки по фотографии, "
                                  "показать список всех парковочных знаков и "
                                  "найти ближайшую парковку.\nПожалуйста, выберите, что Вы хотите сделать.",
                             reply_markup=markup)
            deep_level += 1
        else:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            btn1 = types.KeyboardButton("Вернуться назад")
            markup.add(btn1)
            bot.send_message(message.chat.id, text="Пожалуйста, загрузите фотографию или используйте кнопку.", reply_markup=markup)
    elif deep_level == 4:
        if check_correct_answer(message.text, ["Вернуться назад"]):
            deep_level -= 3
            show_sign_information = False
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            btn1 = types.KeyboardButton("Распознать знаки парковки")
            btn2 = types.KeyboardButton("Посмотреть список всех парковочных знаков")
            btn3 = types.KeyboardButton("Найти ближайшую парковку")
            markup.add(btn1, btn2, btn3)
            bot.send_message(message.chat.id,
                             text="На данный момент я могу помочь распознать знаки парковки по фотографии, "
                                  "показать список всех парковочных знаков и найти "
                                  "ближайшую парковку.\nПожалуйста, выберите, что Вы хотите сделать.",
                             reply_markup=markup)
            deep_level += 1
        elif show_sign_information:
            user_input = message.text.strip().lower()
            if user_input in full_signs_info:
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                btn1 = types.KeyboardButton("Вернуться назад")
                markup.add(btn1)
                signn_info = full_signs_info[user_input]
                response = f"Название: {signn_info['name']}\nОписание: {signn_info['description']}"
                bot.send_message(message.chat.id, text=response, reply_markup=markup)
            else:
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                btn1 = types.KeyboardButton("Вернуться назад")
                markup.add(btn1)
                bot.send_message(message.chat.id, text="Пожалуйста, введите корректный номер "
                                                       "парковочного знака.\nНапример, 3.27", reply_markup=markup)


# реакция бота на отпрвку пользователем фотографии
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    global k
    global waiting_for_photo
    if waiting_for_photo:
        all_signs = []
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        save_path = f"yolov7/{message.from_user.id}_{photo_number}.jpg"
        with open(save_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        result = subprocess.run([
            'python', 'yolov7/detect.py',
            '--weights', 'best2.pt',
            '--source', save_path,
            '--img', '640',
            '--conf', '0.25'
        ], capture_output=True, text=True)
        k = True
        f = result.stdout.split()
        for i in f:
            if k:
                if i == 'traced!':
                    k = False
            elif i != "Done." and k is False:
                if "_" in i:
                    all_signs.append(i)
            else:
                k = True
        all_signs = [s.strip(',') for s in all_signs]
        bot.send_message(message.chat.id,
                         text=generate_response(all_signs))
    else:
        last_bot_message = bot.get_updates()[-1].message
        current_markup = last_bot_message.reply_markup
        bot.send_message(message.chat.id,
                         text="Если Вы хотите распознать дорожный знак, "
                              "пожалуйста, перейдите в соответствующий раздел бота.", reply_markup=current_markup)


# реакция бота на отправку пользователем локации
@bot.message_handler(content_types=['location'])
def handle_location(message):
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        city = get_location_info(lat, lon)
        maps_link = generate_parking_search_link(lat, lon, city)
        if city:
            response = f"Ближайшие парковки в {city}:\n\n"
        else:
            response = "Ближайшие парковки:\n\n"
        response += f"[Открыть в Яндекс.Картах]({maps_link})\n"
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = types.KeyboardButton("Распознать знаки парковки")
        btn2 = types.KeyboardButton("Посмотреть список всех парковочных знаков")
        btn3 = types.KeyboardButton("Найти ближайшую парковку")
        markup.add(btn1, btn2, btn3)
        bot.send_message(
            message.chat.id,
            response,
            reply_markup=markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    else:
        bot.send_message(
            message.chat.id,
            "Пожалуйста, отправьте ваше местоположение через кнопку 'Отправить местоположение'"
        )


bot.polling(none_stop=True, interval=0)
