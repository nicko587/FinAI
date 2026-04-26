# frontend.py
import streamlit as st
import requests
from datetime import date, timedelta
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="FinAI", page_icon="💰", layout="wide")
API_URL = "http://127.0.0.1:8000/api"

if "ai_suggested_category" not in st.session_state:
    st.session_state.ai_suggested_category = "Без категории"
if "ai_suggested_type" not in st.session_state:
    st.session_state.ai_suggested_type = "expense"

st.title("💰 FinAI — Умный учёт для ИП")

# ========== ЗАГРУЗКА ДАННЫХ ==========
@st.cache_data(ttl=60)
def load_categories():
    try:
        r = requests.get(f"{API_URL}/categories", timeout=3)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        st.error(f"❌ Ошибка подключения: {e}")
    return []

@st.cache_data(ttl=30)
def load_transactions():
    try:
        r = requests.get(f"{API_URL}/transactions", timeout=3)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return []

@st.cache_data(ttl=30)
def load_inventory():
    try:
        r = requests.get(f"{API_URL}/inventory", timeout=3)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return []

def create_transaction(desc, amount, tdate, cat_id, tx_type, external_id=None, quantity=None):
    try:
        payload = {
            "description": desc,
            "amount": amount,
            "trans_date": tdate.isoformat(),
            "category_id": cat_id,
            "transaction_type": tx_type,
            "external_id": external_id,
            "quantity": quantity
        }
        r = requests.post(f"{API_URL}/transactions", json=payload, timeout=3)
        return r.status_code == 200
    except:
        return False

def update_category(tx_id, cat_id):
    try:
        r = requests.put(f"{API_URL}/transactions/{tx_id}/category", json={"category_id": cat_id}, timeout=3)
        return r.status_code == 200
    except:
        return False

def predict_category(desc, amount):
    try:
        r = requests.post(f"{API_URL}/predict", json={"description": desc, "amount": amount}, timeout=3)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def import_csv_file(file, bank_template):
    files = {"file": (file.name, file.getvalue(), "application/octet-stream")}
    data = {"bank_template": bank_template}
    try:
        r = requests.post(f"{API_URL}/import/csv", files=files, data=data, timeout=30)
        if r.status_code == 200:
            return r.json()
        else:
            st.error(f"Ошибка сервера: {r.status_code} - {r.text}")
            return None
    except Exception as e:
        st.error(f"Ошибка подключения: {e}")
        return None

def save_imported_transactions(transactions):
    try:
        r = requests.post(f"{API_URL}/import/save", json=transactions, timeout=30)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

# ========== БОКОВАЯ ПАНЕЛЬ ==========
with st.sidebar:
    st.header("➕ Новая операция")
    type_index = 0 if st.session_state.ai_suggested_type == "expense" else 1
    tx_type_label = st.radio(
        "Тип",
        ["Расход", "Доход"],
        horizontal=True,
        index=type_index,
        key="type_radio"
    )
    st.session_state.ai_suggested_type = "expense" if tx_type_label == "Расход" else "income"

    description = st.text_input("Описание", placeholder="купил молоток 1500")
    amount = st.number_input("Сумма (₽)", min_value=0.01, step=100.0)
    trans_date = st.date_input("Дата", date.today())

    categories = load_categories()
    category_names = ["Без категории"] + [c["name"] for c in categories]
    default_cat = st.session_state.ai_suggested_category
    default_idx = category_names.index(default_cat) if default_cat in category_names else 0
    selected_cat_name = st.selectbox("Категория", category_names, index=default_idx)

    if st.button("🤖 AI подскажет категорию"):
        if description and amount > 0:
            pred = predict_category(description, amount)
            if pred:
                for c in categories:
                    if c["id"] == pred["category_id"]:
                        st.success(f"Предлагаю: **{c['name']}** (уверенность {pred['confidence']*100:.0f}%)")
                        st.session_state.ai_suggested_category = c["name"]
                        st.session_state.ai_suggested_type = pred["transaction_type"]
                        st.rerun()
                        break
            else:
                st.error("Ошибка предсказания")
        else:
            st.warning("Заполните описание и сумму")

    if st.button("💾 Сохранить", type="primary"):
        if description and amount > 0:
            cat_id = None
            if selected_cat_name != "Без категории":
                for c in categories:
                    if c["name"] == selected_cat_name:
                        cat_id = c["id"]
                        break
            tx_type_code = "income" if tx_type_label == "Доход" else "expense"
            if create_transaction(description, amount, trans_date, cat_id, tx_type_code):
                st.success("✅ Операция добавлена!")
                st.cache_data.clear()
                st.session_state.ai_suggested_category = "Без категории"
                st.session_state.ai_suggested_type = "expense"
                st.rerun()
            else:
                st.error("❌ Ошибка при сохранении")
        else:
            st.warning("Заполните описание и сумму")

# ========== ОСНОВНАЯ ОБЛАСТЬ ==========
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📊 Дашборд", "📋 Список операций", "📁 Импорт выписки", "📦 Склад", "📈 Прогноз денег", "📦 Прогноз товаров"]
)

with tab1:
    st.header("Финансовый дашборд")
    transactions = load_transactions()
    if transactions:
        df = pd.DataFrame(transactions)
        total_income = df[df["amount"] > 0]["amount"].sum() if len(df[df["amount"] > 0]) > 0 else 0
        total_expense = df[df["amount"] < 0]["amount"].sum() if len(df[df["amount"] < 0]) > 0 else 0
        total_expense = abs(total_expense)
        profit = total_income - total_expense

        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Доходы", f"{total_income:,.0f} ₽")
        col2.metric("📉 Расходы", f"{total_expense:,.0f} ₽")
        col3.metric("📈 Прибыль", f"{profit:,.0f} ₽")

        expense_df = df[df["amount"] < 0].copy()
        if len(expense_df) > 0:
            st.subheader("📊 Расходы по категориям")
            expense_df["amount_abs"] = expense_df["amount"].abs()
            cat_exp = expense_df.groupby("category_name")["amount_abs"].sum().sort_values(ascending=False)
            st.bar_chart(cat_exp)

        income_df = df[df["amount"] > 0].copy()
        if len(income_df) > 0:
            st.subheader("📈 Доходы по категориям")
            cat_inc = income_df.groupby("category_name")["amount"].sum().sort_values(ascending=False)
            st.bar_chart(cat_inc)
    else:
        st.info("Нет операций. Добавьте первую через боковую панель или импортируйте выписку.")

with tab2:
    st.header("Список операций")
    transactions = load_transactions()
    if transactions:
        transactions.sort(key=lambda x: x['trans_date'], reverse=True)
        categories = load_categories()
        cols = st.columns([3, 1, 1.2, 1.5, 1.2, 0.5])
        cols[0].write("**Описание**")
        cols[1].write("**Сумма**")
        cols[2].write("**Дата**")
        cols[3].write("**Категория**")
        cols[4].write("**Проводка**")
        cols[5].write("**✏️**")
        st.divider()
        for tx in transactions[:20]:
            cols = st.columns([3, 1, 1.2, 1.5, 1.2, 0.5])
            cols[0].write(tx["description"])
            amount = tx["amount"]
            color = "green" if amount > 0 else "red"
            cols[1].markdown(f"<span style='color:{color}'>{amount:,.0f} ₽</span>", unsafe_allow_html=True)
            cols[2].write(tx["trans_date"])
            current_cat = tx["category_name"]
            cat_names = ["Без категории"] + [c["name"] for c in categories]
            default_idx = cat_names.index(current_cat) if current_cat in cat_names else 0
            new_cat = cols[3].selectbox("", cat_names, index=default_idx, key=f"cat_{tx['id']}", label_visibility="collapsed")
            if new_cat != current_cat:
                cat_id = None
                if new_cat != "Без категории":
                    for c in categories:
                        if c["name"] == new_cat:
                            cat_id = c["id"]
                            break
                if update_category(tx["id"], cat_id):
                    st.cache_data.clear()
                    st.rerun()
            cols[4].write(f"{tx['debit_account']} → {tx['credit_account']}")
            cols[5].write("")
            st.divider()
    else:
        st.info("Нет операций")

with tab3:
    st.header("📁 Импорт выписки из банка")
    st.markdown("""
    **Поддерживаемые форматы:** CSV, XLSX.
    - **Тинькофф** — колонки: `Дата операции`, `Описание`, `Сумма`
    - **Сбер** — колонки: `Дата`, `Наименование`, `Сумма`
    - **Другой** — система сама определит колонки, содержащие слова "дата", "описание", "сумма"
    """)
    uploaded_file = st.file_uploader("Выберите файл выписки", type=["csv", "xlsx"])
    bank = st.selectbox("Банк", ["Тинькофф", "Сбер", "Другой"])
    if uploaded_file and st.button("📥 Импортировать и сохранить"):
        with st.spinner("Обработка и сохранение..."):
            result = import_csv_file(uploaded_file, bank.lower())
            if result and result["transactions"]:
                to_save = []
                for tx in result["transactions"]:
                    to_save.append({
                        "description": tx["description"],
                        "amount": tx["amount"],
                        "trans_date": tx["date"],
                        "category_id": tx["category_id"],
                        "transaction_type": tx["transaction_type"],
                        "external_id": tx["external_id"]
                    })
                save_result = save_imported_transactions(to_save)
                if save_result:
                    st.success(f"✅ Импортировано и сохранено {save_result['saved']} операций")
                    if save_result['errors']:
                        st.warning(f"Ошибки: {save_result['errors']}")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("❌ Ошибка при сохранении")
            else:
                st.error("❌ Не удалось распознать файл или нет операций")

with tab4:
    st.header("📦 Складской учёт")
    with st.expander("➕ Добавить товар"):
        new_name = st.text_input("Название товара")
        new_qty = st.number_input("Начальное количество", min_value=0.0, step=1.0)
        new_price = st.number_input("Цена за единицу (₽)", min_value=0.01, step=10.0)
        if st.button("Добавить товар"):
            if new_name:
                response = requests.post(f"{API_URL}/inventory", json={"name": new_name, "quantity": new_qty, "unit_price": new_price})
                if response.status_code == 200:
                    st.success("Товар добавлен")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Ошибка добавления")
            else:
                st.warning("Введите название")
    inventory = load_inventory()
    if inventory:
        st.subheader("Текущие остатки")
        for item in inventory:
            col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1.2, 1.5, 0.5])
            col1.write(item['name'])
            col2.write(f"{item['quantity']:.1f} шт.")
            col3.write(f"{item['unit_price']:.2f} ₽ (закуп)")
            with col4:
                change = st.number_input("Изменить кол-во", key=f"change_{item['id']}", step=1.0, format="%.1f", label_visibility="collapsed")
            with col5:
                selling_price = None
                if change < 0:
                    selling_price = st.number_input("Цена продажи (₽/шт)", key=f"price_{item['id']}", min_value=0.01, step=10.0, format="%.2f", label_visibility="collapsed")
                else:
                    st.write("—")
            with col6:
                if st.button("✅", key=f"apply_{item['id']}"):
                    if change != 0:
                        payload = {"quantity_change": change}
                        if change < 0 and selling_price is not None:
                            payload["selling_price"] = selling_price
                        r = requests.put(f"{API_URL}/inventory/{item['id']}", json=payload)
                        if r.status_code == 200:
                            st.success(f"Обновлено. Остаток: {r.json()['new_quantity']:.1f}")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(f"Ошибка: {r.text}")
            st.divider()
    else:
        st.info("Склад пуст. Добавьте товары.")

with tab5:
    st.header("Прогноз денежного потока и кассовых разрывов")
    col1, col2 = st.columns(2)
    start_balance = col1.number_input("Начальный остаток на счёте (₽)", value=10000.0, step=1000.0)
    days = col2.slider("Горизонт прогноза (дней)", 7, 90, 30)
    if st.button("Рассчитать прогноз"):
        with st.spinner("Загрузка данных и расчёт..."):
            response = requests.post(f"{API_URL}/forecast/cashflow", json={"start_balance": start_balance, "days": days})
            if response.status_code == 200:
                data = response.json()
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=data['historical_dates'],
                    y=data['historical_balances'],
                    mode='lines',
                    name='Исторический остаток',
                    line=dict(color='blue')
                ))
                fig.add_trace(go.Scatter(
                    x=data['forecast_dates'],
                    y=data['forecast_balances'],
                    mode='lines',
                    name='Прогноз остатка',
                    line=dict(color='orange', dash='dash')
                ))
                if data['cash_gaps']:
                    gap_dates = [data['forecast_dates'][i] for i in data['cash_gaps']]
                    gap_vals = [data['forecast_balances'][i] for i in data['cash_gaps']]
                    fig.add_trace(go.Scatter(
                        x=gap_dates,
                        y=gap_vals,
                        mode='markers',
                        name='⚠️ Кассовый разрыв',
                        marker=dict(color='red', size=10, symbol='x')
                    ))
                fig.update_layout(
                    title="Прогноз остатка денежных средств",
                    xaxis_title="Дата",
                    yaxis_title="Остаток (₽)",
                    hovermode='x unified'
                )
                st.plotly_chart(fig, use_container_width=True)
                if data['cash_gaps']:
                    st.error(f"⚠️ Внимание! Прогнозируется кассовый разрыв в {len(data['cash_gaps'])} днях.")
                    gap_dates_str = ", ".join([data['forecast_dates'][i] for i in data['cash_gaps']])
                    st.warning(f"Даты возможного дефицита: {gap_dates_str}")
                else:
                    st.success("✅ Кассовых разрывов не ожидается.")
                with st.expander("Детальный прогноз ежедневных потоков"):
                    forecast_df = pd.DataFrame({
                        "Дата": data['forecast_dates'],
                        "Прогнозируемый чистый поток (₽)": data['forecast_daily'],
                        "Прогнозируемый остаток (₽)": data['forecast_balances']
                    })
                    st.dataframe(forecast_df)
            else:
                st.error("Ошибка получения прогноза")

with tab6:
    st.header("Прогноз остатков товаров (на основе истории продаж)")
    response = requests.get(f"{API_URL}/forecast/inventory")
    if response.status_code == 200:
        items = response.json()
        if items:
            data = []
            for item in items:
                data.append({
                    "Товар": item['name'],
                    "Остаток (шт)": item['quantity'],
                    "Продано за 30 дней": item['last_30_days_sales'],
                    "Ср. расход в день": round(item['avg_daily_usage'], 1),
                    "Дней до исчерпания": round(item['days_left'], 1) if item['days_left'] else "—"
                })
            st.dataframe(data)
            low_stock = [item for item in items if item['days_left'] is not None and item['days_left'] < 7]
            if low_stock:
                st.warning("⚠️ Товары, которые закончатся в ближайшие 7 дней:")
                for item in low_stock:
                    st.write(f"- {item['name']}: {item['days_left']:.1f} дней")
        else:
            st.info("Нет товаров на складе")
    else:
        st.error("Не удалось загрузить данные")