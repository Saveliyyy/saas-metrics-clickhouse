"""Независимая сверка: считаем те же метрики в pandas и сравниваем с выгрузкой из ClickHouse.
Если SQL где-то ошибается (джоин размножил строки, неверная граница окна), сверка это поймает.

Запуск после scripts/run_all.sh:
    python src/crosscheck.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def mrr_movements(billing: pd.DataFrame) -> pd.DataFrame:
    billing = billing.copy()
    billing["month"] = pd.to_datetime(billing["month"])
    last_month = billing["month"].max()

    # Месяц оттока = месяц после последнего платежа (если он внутри периода данных)
    churn = billing.groupby("account_id", as_index=False)["month"].max()
    churn["month"] = churn["month"] + pd.DateOffset(months=1)
    churn = churn[churn["month"] <= last_month].assign(mrr=0)

    df = pd.concat([billing[["account_id", "month", "mrr"]], churn], ignore_index=True)
    df = df.sort_values(["account_id", "month"])
    df["prev_mrr"] = df.groupby("account_id")["mrr"].shift(1).fillna(0)
    df["rn"] = df.groupby("account_id").cumcount() + 1
    delta = df["mrr"] - df["prev_mrr"]
    old = df["rn"] > 1

    df["new_mrr"] = np.where(df["rn"] == 1, df["mrr"], 0)
    df["expansion_mrr"] = np.where(old & (delta > 0), delta, 0)
    df["contraction_mrr"] = np.where(old & (delta < 0) & (df["mrr"] > 0), delta, 0)
    df["churned_mrr"] = np.where(old & (df["mrr"] == 0), -df["prev_mrr"], 0)

    out = df.groupby("month").agg(
        total_mrr=("mrr", "sum"),
        new_mrr=("new_mrr", "sum"),
        expansion_mrr=("expansion_mrr", "sum"),
        contraction_mrr=("contraction_mrr", "sum"),
        churned_mrr=("churned_mrr", "sum"),
        paying_accounts=("mrr", lambda s: (s > 0).sum()),
    )
    return out.reset_index()


def cohort_retention(billing: pd.DataFrame) -> pd.DataFrame:
    b = billing.copy()
    b["month"] = pd.to_datetime(b["month"])
    b["cohort_month"] = b.groupby("account_id")["month"].transform("min")
    b["month_number"] = (b["month"].dt.year - b["cohort_month"].dt.year) * 12 + (
        b["month"].dt.month - b["cohort_month"].dt.month
    )
    g = b.groupby(["cohort_month", "month_number"]).agg(active_accounts=("account_id", "nunique"), cohort_mrr=("mrr", "sum"))
    g = g.reset_index()
    first = g[g["month_number"] == 0].set_index("cohort_month")
    g["logo_retention"] = (g["active_accounts"] / g["cohort_month"].map(first["active_accounts"])).round(4)
    g["revenue_retention"] = (g["cohort_mrr"] / g["cohort_month"].map(first["cohort_mrr"])).round(4)
    return g


def compare(name: str, ours: pd.DataFrame, ch: pd.DataFrame, keys: list, cols: list) -> bool:
    merged = ours.merge(ch, on=keys, suffixes=("_pd", "_ch"), how="outer", indicator=True)
    ok = (merged["_merge"] == "both").all()
    for c in cols:
        ok &= np.allclose(merged[f"{c}_pd"], merged[f"{c}_ch"], atol=1e-4)
    print(f"{name}: {'OK' if ok else 'РАСХОЖДЕНИЕ'} ({len(merged)} строк)")
    return bool(ok)


def main() -> None:
    billing = pd.read_csv(ROOT / "data" / "billing_monthly.csv")

    ch_mrr = pd.read_csv(ROOT / "reports" / "mrr_movements.csv", parse_dates=["month"])
    ok1 = compare(
        "MRR movements",
        mrr_movements(billing),
        ch_mrr,
        ["month"],
        ["total_mrr", "new_mrr", "expansion_mrr", "contraction_mrr", "churned_mrr", "paying_accounts"],
    )

    ch_ret = pd.read_csv(ROOT / "reports" / "cohort_retention.csv", parse_dates=["cohort_month"])
    ok2 = compare(
        "Cohort retention",
        cohort_retention(billing),
        ch_ret,
        ["cohort_month", "month_number"],
        ["active_accounts", "cohort_mrr", "logo_retention", "revenue_retention"],
    )

    if not (ok1 and ok2):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
