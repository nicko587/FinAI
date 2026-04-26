# generate_data.py (улучшенный, с шумом)
import pandas as pd
import random
import string
from datetime import datetime, timedelta

# ----- Ключевые слова для категорий (с перекрытиями) -----
KEYWORDS = {
    "Реклама": ["реклама", "яндекс директ", "таргет", "продвижение", "директ", "google"],
    "Транспорт": ["такси", "бензин", "заправка", "метро", "автобус", "проезд", "машина", "ремонт авто"],
    "Инструменты": ["молоток", "отвёртка", "дрель", "перфоратор", "шуруповёрт", "гайка", "болт", "пила", "ремонт"],
    "Аренда": ["аренда", "коммуналка", "офис", "склад", "жку", "квартплата"],
    "Канцтовары": ["бумага", "ручка", "карандаш", "скрепки", "папка", "блокнот"],
    "Обеды": ["обед", "кофе", "ланч", "кафе", "столовая", "пицца", "суши", "ресторан"],
    "Связь": ["интернет", "телефон", "билайн", "мтс", "роутер", "симка", "связь"],
    "Коммунальные": ["свет", "газ", "вода", "отопление", "электричество", "коммунальные"],
    "Доход от продаж": ["оплата", "поступление", "выручка", "продажа", "счёт", "перевод"],
    "Прочие расходы": ["штраф", "пеня", "консультация", "обслуживание", "комиссия", "услуги", "ремонт"],
}

# ----- Контрагенты для длинных описаний -----
CONTRACTORS = {
    "Реклама": ["Яндекс.Директ", "VK Реклама", "Google Ads"],
    "Транспорт": ["Яндекс.Такси", "АЗС Лукойл", "Газпромнефть"],
    "Инструменты": ["Леруа Мерлен", "Петрович", "ОБИ"],
    "Аренда": ["ИП Иванов", "Склад Логистик", "ТЦ Мега"],
    "Канцтовары": ["Комус", "Офисмаг", "Ашан"],
    "Обеды": ["Кафе Уют", "Столовая №1", "Макдоналдс"],
    "Связь": ["Билайн", "МТС", "Ростелеком"],
    "Коммунальные": ["Водоканал", "Энергосбыт", "Газпром"],
    "Доход от продаж": ["ООО Ромашка", "ИП Петров", "Магазин"],
    "Прочие расходы": ["Штраф ГИБДД", "Консультант", "Банк", "Ремонт Сервис"],
}

# ----- Вспомогательные функции -----
def add_typo(word, p=0.15):
    """С вероятностью p заменяет одну букву в слове"""
    if random.random() < p and len(word) > 2:
        idx = random.randint(0, len(word)-1)
        letter = random.choice("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
        return word[:idx] + letter + word[idx+1:]
    return word

def add_noise_word(text, p=0.2):
    """С вероятностью p добавляет случайное слово-паразит"""
    noise = ["срочно", "новый", "дешёвый", "дорогой", "качественный", "недорогой", "супер", "акция", "скидка", "оптом", "очень", "быстро"]
    if random.random() < p:
        return text + " " + random.choice(noise)
    return text

def add_cross_category_word(category, text, p=0.1):
    """С вероятностью p добавляет слово из другой категории"""
    if random.random() < p:
        other_cats = [c for c in KEYWORDS.keys() if c != category]
        other = random.choice(other_cats)
        word = random.choice(KEYWORDS[other])
        # Добавляем в начало или конец
        if random.random() < 0.5:
            return word + " " + text
        else:
            return text + " " + word
    return text

def generate_short_description(category):
    """Короткое описание (1-2 ключевых слова)"""
    words = random.sample(KEYWORDS[category], k=random.randint(1, 2))
    text = " ".join(words)
    # Добавляем шум
    text = add_typo(text)
    text = add_noise_word(text)
    text = add_cross_category_word(category, text)
    return text.capitalize()

def generate_long_description(category):
    """Длинное описание с контрагентом и ключевыми словами"""
    contractor = random.choice(CONTRACTORS.get(category, ["Контрагент"]))
    kw = random.choice(KEYWORDS[category])
    templates = [
        f"{contractor} {kw}",
        f"{kw} в {contractor}",
        f"Оплата {contractor} ({kw})",
        f"{contractor}: {kw}",
    ]
    text = random.choice(templates)
    # Добавляем шум
    text = add_typo(text)
    text = add_noise_word(text)
    text = add_cross_category_word(category, text)
    return text.capitalize()

def generate_ambiguous_description(category):
    """Неоднозначное описание — без явных ключевых слов (только контрагент или общая фраза)"""
    if category == "Доход от продаж":
        templates = ["Поступление от клиента", "Оплата по счёту", "Выручка"]
    else:
        templates = ["Оплата поставщику", "Перевод средств", "Списание", "Расходная операция"]
    text = random.choice(templates)
    text = add_typo(text)
    text = add_noise_word(text)
    return text

def generate_row(date):
    # Распределение: 60% расходы, 40% доходы
    if random.random() < 0.6:
        cat = random.choice([
            "Реклама", "Транспорт", "Инструменты", "Аренда",
            "Канцтовары", "Обеды", "Связь", "Коммунальные", "Прочие расходы"
        ])
        amount = round(random.uniform(50, 50000), 2)
        tx_type = "expense"
    else:
        cat = "Доход от продаж"
        amount = round(random.uniform(1000, 200000), 2)
        tx_type = "income"

    # Тип описания: 50% короткие, 40% длинные, 10% неоднозначные
    r = random.random()
    if r < 0.5:
        description = generate_short_description(cat)
    elif r < 0.9:
        description = generate_long_description(cat)
    else:
        description = generate_ambiguous_description(cat)

    return {
        "date": date.strftime("%Y-%m-%d"),
        "description": description,
        "amount": amount,
        "category": cat,
        "type": tx_type
    }

# ----- Генерация 20 000 записей -----
start_date = datetime.now() - timedelta(days=730)
rows = []
for i in range(20000):
    random_days = random.randint(0, 730)
    date = start_date + timedelta(days=random_days)
    rows.append(generate_row(date))

df = pd.DataFrame(rows)
df.to_csv("synthetic_transactions.csv", index=False)
print(f"✅ Сгенерировано {len(df)} записей")
print(df.head(20))