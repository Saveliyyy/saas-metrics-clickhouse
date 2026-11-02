"""Генерация синтетических данных B2B SaaS-платформы (почта, календарь, ВКС, мессенджер).

Три таблицы:
  accounts           — компании-клиенты: дата подключения, тариф, размер, отрасль
  billing_monthly    — ежемесячные начисления: число лицензий × цена (из них считается MRR)
  product_activity   — активность пользователей: кто, когда и каким продуктом пользовался

В данные заложены реалистичные эффекты: часть клиентов уходит (churn), часть
докупает лицензии (expansion), крупные клиенты уходят реже, мессенджер используют чаще ВКС.
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 7
N_ACCOUNTS = 600
START = pd.Timestamp("2025-01-01")
END = pd.Timestamp("2026-06-30")
ACTIVITY_DAYS = 120  # активность генерируем за последние 4 месяца, чтобы не раздувать объём

PLANS = {"basic": 250, "business": 450, "enterprise": 700}  # ₽ за лицензию в месяц
# (доля пользователей, которые вообще начали пользоваться продуктом; вероятность активности в рабочий день)
PRODUCTS = {"mail": (0.98, 0.85), "calendar": (0.70, 0.55), "messenger": (0.60, 0.65), "vks": (0.40, 0.25)}
AT_RISK_SHARE = 0.08  # доля платящих клиентов, у которых активность падает в последние 6 недель
OUT = Path(__file__).resolve().parents[1] / "data"


def make_accounts(rng) -> pd.DataFrame:
    months = pd.date_range(START, END, freq="MS")
    # Привлечение растёт со временем
    weights = np.linspace(1, 2.5, len(months))
    signup = rng.choice(months, size=N_ACCOUNTS, p=weights / weights.sum())
    size = rng.choice(["small", "medium", "large"], size=N_ACCOUNTS, p=[0.6, 0.3, 0.1])
    plan = np.where(
        size == "large",
        rng.choice(list(PLANS), size=N_ACCOUNTS, p=[0.1, 0.4, 0.5]),
        rng.choice(list(PLANS), size=N_ACCOUNTS, p=[0.55, 0.4, 0.05]),
    )
    seats0 = np.select(
        [size == "small", size == "medium"],
        [rng.integers(5, 30, N_ACCOUNTS), rng.integers(30, 150, N_ACCOUNTS)],
        rng.integers(150, 800, N_ACCOUNTS),
    )
    industry = rng.choice(["retail", "it", "finance", "manufacturing", "public"], size=N_ACCOUNTS)
    return pd.DataFrame(
        {
            "account_id": np.arange(1, N_ACCOUNTS + 1),
            "signup_month": pd.to_datetime(signup).date,
            "size_segment": size,
            "plan": plan,
            "industry": industry,
            "initial_seats": seats0,
        }
    )


def make_billing(accounts: pd.DataFrame, rng) -> pd.DataFrame:
    rows = []
    churn_p = {"small": 0.045, "medium": 0.025, "large": 0.01}
    for acc in accounts.itertuples():
        seats = acc.initial_seats
        price = PLANS[acc.plan]
        for month in pd.date_range(acc.signup_month, END, freq="MS"):
            rows.append((acc.account_id, month.date(), seats, price, seats * price))
            if rng.random() < churn_p[acc.size_segment]:
                break  # клиент ушёл, начислений дальше нет
            r = rng.random()
            if r < 0.12:
                seats = int(seats * rng.uniform(1.05, 1.3)) + 1  # докупили лицензии
            elif r < 0.17:
                seats = max(1, int(seats * rng.uniform(0.75, 0.95)))  # сократили
    return pd.DataFrame(rows, columns=["account_id", "month", "seats", "price_per_seat", "mrr"])


def make_activity(accounts: pd.DataFrame, billing: pd.DataFrame, rng) -> pd.DataFrame:
    """Дневная активность. Чтобы объём был разумным, у каждого клиента берём до 40 пользователей."""
    days = pd.date_range(END - pd.Timedelta(days=ACTIVITY_DAYS - 1), END, freq="D")
    last_paid = billing.groupby("account_id")["month"].max()
    first_paid = billing.groupby("account_id")["month"].min()
    frames = []
    for acc in accounts.itertuples():
        n_users = min(acc.initial_seats, 40)
        user_ids = acc.account_id * 10_000 + np.arange(n_users)
        engagement = rng.beta(4, 2, n_users)  # у каждого пользователя своя «вовлечённость»
        start = pd.Timestamp(first_paid[acc.account_id])
        end = pd.Timestamp(last_paid[acc.account_id]) + pd.offsets.MonthEnd(0)
        active_days = days[(days >= start) & (days <= end)]
        if len(active_days) == 0:
            continue
        weekend = np.isin(active_days.dayofweek, [5, 6])
        day_factor = np.where(weekend, 0.15, 1.0)

        # Перед уходом активность затухает: у ушедших — за 6 недель до конца подписки,
        # у части текущих клиентов — в последние 6 недель (их и должен найти 05_churn_risk.sql).
        churned = end < END
        at_risk = (not churned) and rng.random() < AT_RISK_SHARE
        if churned or at_risk:
            days_to_end = (end - active_days).days.to_numpy()
            day_factor = day_factor * np.clip(days_to_end / 42, 0.15, 1.0)

        for product, (adoption, p) in PRODUCTS.items():
            adopted = rng.random(n_users) < adoption
            prob = np.outer(engagement * p * adopted, day_factor)
            hit = rng.random(prob.shape) < prob
            u_idx, d_idx = np.nonzero(hit)
            frames.append(
                pd.DataFrame(
                    {
                        "event_date": active_days[d_idx].date,
                        "account_id": acc.account_id,
                        "user_id": user_ids[u_idx],
                        "product": product,
                        "events": rng.poisson(8 * p, len(u_idx)) + 1,
                    }
                )
            )
    return pd.concat(frames, ignore_index=True).sort_values(["event_date", "account_id"]).reset_index(drop=True)


def main() -> None:
    rng = np.random.default_rng(SEED)
    OUT.mkdir(exist_ok=True)
    accounts = make_accounts(rng)
    billing = make_billing(accounts, rng)
    activity = make_activity(accounts, billing, rng)
    accounts.to_csv(OUT / "accounts.csv", index=False)
    billing.to_csv(OUT / "billing_monthly.csv", index=False)
    activity.to_csv(OUT / "product_activity.csv", index=False)
    print(f"accounts: {len(accounts):,} | billing: {len(billing):,} | activity: {len(activity):,} строк")


if __name__ == "__main__":
    main()
