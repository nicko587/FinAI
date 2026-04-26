# train_model.py
import pandas as pd
import pickle
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb

df = pd.read_csv("synthetic_transactions.csv")
print(f"Загружено {len(df)} записей")

label_encoder = LabelEncoder()
y_encoded = label_encoder.fit_transform(df["category"])
with open("label_encoder.pkl", "wb") as f:
    pickle.dump(label_encoder, f)

X_text = df["description"].values
X_amount = df["amount"].values.reshape(-1, 1)

vectorizer = TfidfVectorizer(
    max_features=300,
    lowercase=True,
    ngram_range=(1, 1),
    stop_words=['купил', 'оплата', 'перевод', 'за', 'на', 'в', 'с', 'по', 'у', 'и', 'к', 'от']
)
X_text_vec = vectorizer.fit_transform(X_text).toarray()
feature_names = vectorizer.get_feature_names_out().tolist()
feature_names.append("log_amount")

X = np.hstack([X_text_vec, X_amount])
X[:, -1] = np.log1p(X[:, -1])

X_train, X_test, y_train, y_test = train_test_split(X, y_encoded, test_size=0.2, random_state=42)

model = xgb.XGBClassifier(
    n_estimators=150,
    max_depth=5,
    learning_rate=0.1,
    objective='multi:softprob',
    random_state=42,
    reg_alpha=0.5,
    reg_lambda=1.5,
    subsample=0.8,
    colsample_bytree=0.8,
    early_stopping_rounds=10,
    eval_metric='mlogloss'
)

# Обучаем с валидационной выборкой для ранней остановки
eval_set = [(X_test, y_test)]
model.fit(X_train, y_train, eval_set=eval_set, verbose=False)

y_pred = model.predict(X_test)
print(classification_report(y_test, y_pred, target_names=label_encoder.classes_))

with open("model.pkl", "wb") as f:
    pickle.dump(model, f)
with open("vectorizer.pkl", "wb") as f:
    pickle.dump(vectorizer, f)
with open("feature_names.pkl", "wb") as f:
    pickle.dump(feature_names, f)

print("✅ Модель сохранена (с ранней остановкой)")