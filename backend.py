# backend.py
import pickle
import numpy as np
import pandas as pd
import io
import hashlib
import csv
import re
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import date, datetime, timedelta
from typing import List, Optional
from enum import Enum
from statsmodels.tsa.holtwinters import ExponentialSmoothing
import warnings
warnings.filterwarnings("ignore")

# ========== ПЛАН СЧЕТОВ ==========
class AccountType(str, Enum):
    ACTIVE = "active"
    PASSIVE = "passive"
    EXPENSE = "expense"
    INCOME = "income"

class Account:
    def __init__(self, code: str, name: str, account_type: AccountType):
        self.code = code
        self.name = name
        self.type = account_type

CHART_OF_ACCOUNTS = {
    "51": Account("51", "Расчётный счёт", AccountType.ACTIVE),
    "50": Account("50", "Касса", AccountType.ACTIVE),
    "60": Account("60", "Расчёты с поставщиками", AccountType.PASSIVE),
    "68": Account("68", "Расчёты по налогам", AccountType.PASSIVE),
    "70": Account("70", "Расчёты с персоналом", AccountType.PASSIVE),
    "80": Account("80", "Уставный капитал", AccountType.PASSIVE),
    "20": Account("20", "Основное производство", AccountType.EXPENSE),
    "26": Account("26", "Общехозяйственные расходы", AccountType.EXPENSE),
    "44": Account("44", "Расходы на продажу", AccountType.EXPENSE),
    "90.01": Account("90.01", "Выручка", AccountType.INCOME),
    "91.01": Account("91.01", "Прочие доходы", AccountType.INCOME),
    "91.02": Account("91.02", "Прочие расходы", AccountType.EXPENSE),
}

def get_default_accounts(transaction_type: str, category_name: str):
    if transaction_type == "income":
        if "продаж" in category_name.lower():
            return "51", "90.01"
        else:
            return "51", "91.01"
    else:
        if category_name in ["Реклама", "Транспорт", "Инструменты", "Аренда", "Канцтовары", "Обеды", "Связь", "Коммунальные", "Товары", "Себестоимость продаж"]:
            return "26", "51"
        else:
            return "91.02", "51"

def validate_double_entry(debit: str, credit: str, amount: float):
    if debit not in CHART_OF_ACCOUNTS:
        raise HTTPException(400, f"Счёт дебета {debit} не найден")
    if credit not in CHART_OF_ACCOUNTS:
        raise HTTPException(400, f"Счёт кредита {credit} не найден")
    if debit == credit:
        raise HTTPException(400, "Дебет и кредит не могут совпадать")
    if amount <= 0:
        raise HTTPException(400, "Сумма должна быть положительной")
    return True

# ========== БАЗА ДАННЫХ ==========
DATABASE_URL = "sqlite:///./finai.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ========== МОДЕЛИ ==========
class CategoryDB(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    color = Column(String, default="#4CAF50")

class TransactionDB(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, default=1, nullable=False)
    external_id = Column(String, unique=True, nullable=True)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    trans_date = Column(Date, nullable=False)
    category_id = Column(Integer, nullable=True)
    category_name = Column(String, default="Без категории")
    transaction_type = Column(String, default="expense")
    debit_account = Column(String(10), nullable=False, default="26")
    credit_account = Column(String(10), nullable=False, default="51")
    quantity = Column(Float, nullable=True)          # количество товара (при закупке/продаже)
    created_at = Column(DateTime, server_default=func.now())

class InventoryDB(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, default=1, nullable=False)
    name = Column(String, nullable=False)
    quantity = Column(Float, default=0)
    unit_price = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

def init_categories(db: Session):
    if db.query(CategoryDB).count() == 0:
        defaults = [
            ("Реклама", "#FF5722"),
            ("Транспорт", "#2196F3"),
            ("Инструменты", "#4CAF50"),
            ("Аренда", "#9C27B0"),
            ("Канцтовары", "#FF9800"),
            ("Обеды", "#F44336"),
            ("Связь", "#00BCD4"),
            ("Коммунальные", "#3F51B5"),
            ("Доход от продаж", "#8BC34A"),
            ("Прочие расходы", "#9E9E9E"),
            ("Товары", "#FFA07A"),
            ("Себестоимость продаж", "#CD5C5C"),
        ]
        for name, color in defaults:
            db.add(CategoryDB(name=name, color=color))
        db.commit()
        print("✅ Созданы категории по умолчанию")

# ========== PYDANTIC СХЕМЫ ==========
class CategoryResponse(BaseModel):
    id: int
    name: str
    color: str

class TransactionCreate(BaseModel):
    description: str
    amount: float
    trans_date: date
    category_id: Optional[int] = None
    transaction_type: str = "expense"
    external_id: Optional[str] = None
    quantity: Optional[float] = None

class TransactionResponse(BaseModel):
    id: int
    description: str
    amount: float
    trans_date: date
    category_name: str
    transaction_type: str
    debit_account: str
    credit_account: str
    quantity: Optional[float] = None

class UpdateCategoryRequest(BaseModel):
    category_id: Optional[int] = None

class PredictRequest(BaseModel):
    description: str
    amount: float

class PredictResponse(BaseModel):
    category_id: int
    category_name: str
    confidence: float
    transaction_type: str

class InventoryItem(BaseModel):
    id: int
    name: str
    quantity: float
    unit_price: float

class InventoryCreate(BaseModel):
    name: str
    quantity: float = 0
    unit_price: float

class InventoryUpdate(BaseModel):
    quantity_change: float
    selling_price: Optional[float] = None
    description: str = ""

# ========== ML ==========
MODEL = None
VECTORIZER = None
LABEL_ENCODER = None

def load_ml_models():
    global MODEL, VECTORIZER, LABEL_ENCODER
    try:
        with open("model.pkl", "rb") as f:
            MODEL = pickle.load(f)
        with open("vectorizer.pkl", "rb") as f:
            VECTORIZER = pickle.load(f)
        with open("label_encoder.pkl", "rb") as f:
            LABEL_ENCODER = pickle.load(f)
        print("✅ ML модели загружены")
        return True
    except FileNotFoundError as e:
        print(f"⚠️ ML модели не найдены: {e}")
        return False

def internal_predict(description: str, amount: float, db: Session):
    if MODEL is None or VECTORIZER is None:
        cat = db.query(CategoryDB).first()
        return {"category_id": cat.id, "category_name": cat.name, "confidence": 0.5, "transaction_type": "expense"}
    text_vec = VECTORIZER.transform([description]).toarray()
    amount_log = np.log1p(amount)
    X_input = np.hstack([text_vec, [[amount_log]]])
    pred_num = MODEL.predict(X_input)[0]
    pred_cat = LABEL_ENCODER.inverse_transform([pred_num])[0]
    probs = MODEL.predict_proba(X_input)[0]
    confidence = float(max(probs))
    tx_type = "income" if pred_cat == "Доход от продаж" else "expense"
    cat = db.query(CategoryDB).filter(CategoryDB.name == pred_cat).first()
    if not cat:
        cat = db.query(CategoryDB).first()
    return {"category_id": cat.id, "category_name": cat.name, "confidence": confidence, "transaction_type": tx_type}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    db = SessionLocal()
    try:
        init_categories(db)
        load_ml_models()
        print("✅ База данных готова")
    finally:
        db.close()

@app.get("/")
def root():
    return {"status": "ok", "message": "FinAI Backend"}

@app.get("/api/categories", response_model=List[CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    return db.query(CategoryDB).all()

@app.post("/api/transactions", response_model=TransactionResponse)
def create_transaction(tx: TransactionCreate, db: Session = Depends(get_db)):
    category_name = "Без категории"
    if tx.category_id:
        cat = db.query(CategoryDB).filter(CategoryDB.id == tx.category_id).first()
        if cat:
            category_name = cat.name
    debit, credit = get_default_accounts(tx.transaction_type, category_name)
    validate_double_entry(debit, credit, tx.amount)
    signed_amount = tx.amount if tx.transaction_type == "income" else -tx.amount
    new_tx = TransactionDB(
        user_id=1,
        external_id=tx.external_id,
        description=tx.description,
        amount=signed_amount,
        trans_date=tx.trans_date,
        category_id=tx.category_id,
        category_name=category_name,
        transaction_type=tx.transaction_type,
        debit_account=debit,
        credit_account=credit,
        quantity=tx.quantity
    )
    db.add(new_tx)
    db.commit()
    db.refresh(new_tx)
    return TransactionResponse(
        id=new_tx.id,
        description=new_tx.description,
        amount=new_tx.amount,
        trans_date=new_tx.trans_date,
        category_name=new_tx.category_name,
        transaction_type=new_tx.transaction_type,
        debit_account=new_tx.debit_account,
        credit_account=new_tx.credit_account,
        quantity=new_tx.quantity
    )

@app.get("/api/transactions", response_model=List[TransactionResponse])
def get_transactions(db: Session = Depends(get_db)):
    txs = db.query(TransactionDB).filter(TransactionDB.user_id == 1).order_by(
        TransactionDB.trans_date.desc(),
        TransactionDB.id.desc()
    ).all()
    return [
        TransactionResponse(
            id=t.id,
            description=t.description,
            amount=t.amount,
            trans_date=t.trans_date,
            category_name=t.category_name,
            transaction_type=t.transaction_type,
            debit_account=t.debit_account,
            credit_account=t.credit_account,
            quantity=t.quantity
        ) for t in txs
    ]

@app.put("/api/transactions/{tx_id}/category")
def update_category(tx_id: int, req: UpdateCategoryRequest, db: Session = Depends(get_db)):
    tx = db.query(TransactionDB).filter(TransactionDB.id == tx_id).first()
    if not tx:
        raise HTTPException(404, "Операция не найдена")
    if req.category_id is None:
        tx.category_id = None
        tx.category_name = "Без категории"
    else:
        cat = db.query(CategoryDB).filter(CategoryDB.id == req.category_id).first()
        if not cat:
            raise HTTPException(404, "Категория не найдена")
        tx.category_id = cat.id
        tx.category_name = cat.name
        debit, credit = get_default_accounts(tx.transaction_type, cat.name)
        validate_double_entry(debit, credit, abs(tx.amount))
        tx.debit_account = debit
        tx.credit_account = credit
    db.commit()
    return {"status": "updated", "transaction_id": tx_id, "category_name": tx.category_name}

@app.post("/api/predict", response_model=PredictResponse)
def predict_category(req: PredictRequest, db: Session = Depends(get_db)):
    if MODEL is None or VECTORIZER is None:
        raise HTTPException(503, "ML модель не загружена")
    result = internal_predict(req.description, req.amount, db)
    return PredictResponse(**result)

# ========== ИМПОРТ CSV ==========
def generate_external_id(date_str, amount, description):
    raw = f"{date_str}|{amount}|{description}"
    return hashlib.md5(raw.encode()).hexdigest()

@app.post("/api/import/csv")
async def import_csv(
    file: UploadFile = File(...),
    bank_template: str = Form(...),
    db: Session = Depends(get_db)
):
    contents = await file.read()
    filename = file.filename.lower()
    try:
        if filename.endswith('.csv'):
            content_str = contents.decode('utf-8-sig')
            for sep in [',', '\t', ';']:
                try:
                    df = pd.read_csv(io.StringIO(content_str), sep=sep, encoding='utf-8')
                    if len(df.columns) > 1:
                        break
                except:
                    continue
            else:
                raise ValueError("Не удалось определить разделитель CSV")
        elif filename.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(contents), engine='openpyxl')
        else:
            raise HTTPException(400, "Файл должен быть CSV или XLSX")
    except Exception as e:
        raise HTTPException(400, f"Ошибка чтения файла: {str(e)}")
    if bank_template == "tinkoff":
        required = ["Дата операции", "Описание", "Сумма"]
        if not all(col in df.columns for col in required):
            raise HTTPException(400, f"Для Тинькофф нужны колонки: {required}. Найдены: {list(df.columns)}")
        df = df.rename(columns={
            "Дата операции": "date",
            "Описание": "description",
            "Сумма": "amount"
        })
    elif bank_template == "sber":
        required = ["Дата", "Наименование", "Сумма"]
        if not all(col in df.columns for col in required):
            raise HTTPException(400, f"Для Сбера нужны колонки: {required}. Найдены: {list(df.columns)}")
        df = df.rename(columns={
            "Дата": "date",
            "Наименование": "description",
            "Сумма": "amount"
        })
    else:
        possible_date = [c for c in df.columns if 'дата' in c.lower() or 'date' in c.lower()]
        possible_desc = [c for c in df.columns if 'опис' in c.lower() or 'description' in c.lower() or 'наимен' in c.lower()]
        possible_amount = [c for c in df.columns if 'сумм' in c.lower() or 'amount' in c.lower()]
        if possible_date and possible_desc and possible_amount:
            df = df.rename(columns={
                possible_date[0]: "date",
                possible_desc[0]: "description",
                possible_amount[0]: "amount"
            })
        else:
            raise HTTPException(400, f"Не удалось определить колонки для шаблона 'Другой'. Найдены: {list(df.columns)}")
    df["date"] = pd.to_datetime(df["date"], errors='coerce').dt.date
    df = df.dropna(subset=["date"])
    result_transactions = []
    duplicates_skipped = 0
    for _, row in df.iterrows():
        amount_raw = row["amount"]
        if pd.isna(amount_raw):
            continue
        if amount_raw < 0:
            tx_type = "expense"
            amount_abs = abs(amount_raw)
        else:
            tx_type = "income"
            amount_abs = amount_raw
        description = str(row["description"]).strip()
        trans_date = row["date"]
        ext_id = generate_external_id(str(trans_date), amount_abs, description)
        existing = db.query(TransactionDB).filter(TransactionDB.external_id == ext_id).first()
        if existing:
            duplicates_skipped += 1
            continue
        pred = internal_predict(description, amount_abs, db)
        result_transactions.append({
            "date": trans_date.isoformat(),
            "description": description,
            "amount": amount_abs,
            "transaction_type": tx_type,
            "category_id": pred["category_id"],
            "category_name": pred["category_name"],
            "confidence": pred["confidence"],
            "external_id": ext_id
        })
    return {"transactions": result_transactions, "duplicates_skipped": duplicates_skipped}

@app.post("/api/import/save")
def save_imported_transactions(transactions: List[TransactionCreate], db: Session = Depends(get_db)):
    saved = 0
    errors = []
    for tx_data in transactions:
        try:
            if tx_data.external_id:
                existing = db.query(TransactionDB).filter(TransactionDB.external_id == tx_data.external_id).first()
                if existing:
                    errors.append(f"Дубликат: {tx_data.external_id}")
                    continue
            category_name = "Без категории"
            if tx_data.category_id:
                cat = db.query(CategoryDB).filter(CategoryDB.id == tx_data.category_id).first()
                if cat:
                    category_name = cat.name
            debit, credit = get_default_accounts(tx_data.transaction_type, category_name)
            signed_amount = tx_data.amount if tx_data.transaction_type == "income" else -tx_data.amount
            new_tx = TransactionDB(
                user_id=1,
                external_id=tx_data.external_id,
                description=tx_data.description,
                amount=signed_amount,
                trans_date=tx_data.trans_date,
                category_id=tx_data.category_id,
                category_name=category_name,
                transaction_type=tx_data.transaction_type,
                debit_account=debit,
                credit_account=credit
            )
            db.add(new_tx)
            saved += 1
        except Exception as e:
            errors.append(str(e))
    db.commit()
    print(f"[DEBUG] Сохранено транзакций: {saved}, ошибки: {errors}")
    return {"saved": saved, "errors": errors}

# ========== СКЛАДСКОЙ УЧЁТ ==========
@app.post("/api/inventory", response_model=InventoryItem)
def add_inventory_item(item: InventoryCreate, db: Session = Depends(get_db)):
    new_item = InventoryDB(user_id=1, name=item.name, quantity=item.quantity, unit_price=item.unit_price)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(db: Session = Depends(get_db)):
    return db.query(InventoryDB).filter(InventoryDB.user_id == 1).all()

@app.put("/api/inventory/{item_id}")
def update_inventory(item_id: int, upd: InventoryUpdate, db: Session = Depends(get_db)):
    item = db.query(InventoryDB).filter(InventoryDB.id == item_id, InventoryDB.user_id == 1).first()
    if not item:
        raise HTTPException(404, "Товар не найден")
    new_qty = item.quantity + upd.quantity_change
    if new_qty < 0:
        raise HTTPException(400, "Недостаточно товара на складе")
    item.quantity = new_qty

    if upd.quantity_change > 0:
        # Приход (закупка)
        amount = upd.quantity_change * item.unit_price
        cat = db.query(CategoryDB).filter(CategoryDB.name == "Товары").first()
        if not cat:
            cat = db.query(CategoryDB).first()
        debit, credit = get_default_accounts("expense", "Товары")
        new_tx = TransactionDB(
            user_id=1,
            description=f"Закупка {item.name} x{upd.quantity_change} на сумму {amount:.2f}₽",
            amount=-amount,
            trans_date=date.today(),
            category_id=cat.id,
            category_name="Товары",
            transaction_type="expense",
            debit_account=debit,
            credit_account=credit,
            quantity=upd.quantity_change
        )
        db.add(new_tx)
    else:
        # Продажа
        if upd.selling_price is None:
            raise HTTPException(400, "Для продажи укажите цену продажи")
        qty_sold = -upd.quantity_change
        cost = qty_sold * item.unit_price
        revenue = qty_sold * upd.selling_price
        # Доход (выручка)
        inc_cat = db.query(CategoryDB).filter(CategoryDB.name == "Доход от продаж").first()
        if not inc_cat:
            inc_cat = db.query(CategoryDB).first()
        debit_inc, credit_inc = get_default_accounts("income", "Доход от продаж")
        inc_tx = TransactionDB(
            user_id=1,
            description=f"Продажа {item.name} x{qty_sold} по цене {upd.selling_price:.2f}₽ (выручка {revenue:.2f}₽)",
            amount=revenue,
            trans_date=date.today(),
            category_id=inc_cat.id,
            category_name="Доход от продаж",
            transaction_type="income",
            debit_account=debit_inc,
            credit_account=credit_inc,
            quantity=qty_sold
        )
        db.add(inc_tx)
        # Расход (себестоимость)
        exp_cat = db.query(CategoryDB).filter(CategoryDB.name == "Себестоимость продаж").first()
        if not exp_cat:
            exp_cat = db.query(CategoryDB).first()
        debit_exp, credit_exp = get_default_accounts("expense", "Себестоимость продаж")
        exp_tx = TransactionDB(
            user_id=1,
            description=f"Себестоимость продажи {item.name} x{qty_sold} (закупочная цена {item.unit_price:.2f}₽)",
            amount=-cost,
            trans_date=date.today(),
            category_id=exp_cat.id,
            category_name="Себестоимость продаж",
            transaction_type="expense",
            debit_account=debit_exp,
            credit_account=credit_exp,
            quantity=qty_sold
        )
        db.add(exp_tx)
    db.commit()
    return {"status": "updated", "new_quantity": item.quantity}

# ========== ПРОГНОЗ КАССОВЫХ РАЗРЫВОВ ==========
@app.post("/api/forecast/cashflow")
def forecast_cashflow(request: dict, db: Session = Depends(get_db)):
    start_balance = request.get("start_balance", 0.0)
    days = request.get("days", 30)
    end_date = date.today()
    start_date = end_date - timedelta(days=90)
    txs = db.query(TransactionDB).filter(
        TransactionDB.user_id == 1,
        TransactionDB.trans_date >= start_date,
        TransactionDB.trans_date <= end_date
    ).all()
    if not txs:
        raise HTTPException(400, "Недостаточно данных для прогноза")
    df = pd.DataFrame([(t.trans_date, t.amount) for t in txs], columns=['date', 'amount'])
    df = df.groupby('date')['amount'].sum().reset_index()
    df = df.set_index('date').asfreq('D', fill_value=0)
    model = ExponentialSmoothing(df['amount'], trend=None, seasonal=None, initialization_method="estimated")
    fit = model.fit()
    forecast_values = fit.forecast(days)
    # Кумулятивный остаток
    historical_balance = []
    balance = start_balance
    for dt in pd.date_range(start_date, end_date):
        daily_amount = df['amount'].get(dt, 0)
        balance += daily_amount
        historical_balance.append(balance)
    forecast_balance = []
    balance_last = historical_balance[-1] if historical_balance else start_balance
    for f in forecast_values:
        balance_last += f
        forecast_balance.append(balance_last)
    gaps = [i for i, val in enumerate(forecast_balance) if val < 0]
    forecast_dates = (pd.date_range(end_date + timedelta(days=1), periods=days)).strftime("%Y-%m-%d").tolist()
    historical_dates = pd.date_range(start_date, end_date).strftime("%Y-%m-%d").tolist()
    return {
        "historical_dates": historical_dates,
        "historical_balances": historical_balance,
        "forecast_dates": forecast_dates,
        "forecast_balances": forecast_balance,
        "cash_gaps": gaps,
        "forecast_daily": forecast_values.tolist()
    }

# ========== ПРОГНОЗ ТОВАРНЫХ ОСТАТКОВ (АВТОМАТИЧЕСКИЙ) ==========
@app.get("/api/forecast/inventory")
def forecast_inventory(db: Session = Depends(get_db)):
    items = db.query(InventoryDB).filter(InventoryDB.user_id == 1).all()
    today = date.today()
    start_date = today - timedelta(days=30)
    result = []
    for item in items:
        # Ищем транзакции продаж (расходные с категорией "Себестоимость продаж" и содержащие название товара)
        sales_txs = db.query(TransactionDB).filter(
            TransactionDB.user_id == 1,
            TransactionDB.transaction_type == "expense",
            TransactionDB.category_name == "Себестоимость продаж",
            TransactionDB.description.like(f"%{item.name}%"),
            TransactionDB.trans_date >= start_date
        ).all()
        total_quantity = 0.0
        # Сначала пробуем взять из поля quantity
        for tx in sales_txs:
            if tx.quantity is not None:
                total_quantity += tx.quantity
        # Если нет, парсим описание (x число)
        if total_quantity == 0:
            for tx in sales_txs:
                match = re.search(r'x(\d+(?:\.\d+)?)', tx.description)
                if match:
                    total_quantity += float(match.group(1))
        days = (today - start_date).days if (today - start_date).days > 0 else 1
        avg_daily = total_quantity / days
        days_left = item.quantity / avg_daily if avg_daily > 0 else None
        result.append({
            "id": item.id,
            "name": item.name,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "avg_daily_usage": avg_daily,
            "days_left": days_left,
            "last_30_days_sales": total_quantity
        })
    return result

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("🚀 Запуск FinAI Backend (полная функциональность)")
    print("📡 http://127.0.0.1:8000")
    print("=" * 50)
    uvicorn.run(app, host="127.0.0.1", port=8000)