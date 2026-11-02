"""Дашборд продуктовых метрик на Plotly. Читает выгрузки из reports/ и собирает один HTML.

Запуск после scripts/run_all.sh:
    python src/dashboard.py
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

COLORS = {
    "new_mrr": "#2E7D32",
    "expansion_mrr": "#81C784",
    "contraction_mrr": "#FFB74D",
    "churned_mrr": "#E53935",
}
LABELS = {
    "new_mrr": "Новые клиенты",
    "expansion_mrr": "Расширение",
    "contraction_mrr": "Сокращение",
    "churned_mrr": "Отток",
}


def build() -> go.Figure:
    mrr = pd.read_csv(REPORTS / "mrr_movements.csv", parse_dates=["month"])
    ret = pd.read_csv(REPORTS / "cohort_retention.csv", parse_dates=["cohort_month"])
    eng = pd.read_csv(REPORTS / "engagement.csv")

    fig = make_subplots(
        rows=3,
        cols=2,
        specs=[[{"colspan": 2, "secondary_y": True}, None], [{}, {}], [{"colspan": 2}, None]],
        subplot_titles=(
            "MRR и его компоненты, ₽",
            "Удержание клиентов по когортам (logo retention)",
            "Липкость продуктов: DAU / MAU",
            "Удержание выручки по когортам (NRR), %",
        ),
        vertical_spacing=0.09,
        row_heights=[0.32, 0.3, 0.38],
    )

    # 1. Декомпозиция MRR: столбики изменений + линия итогового MRR
    for col, color in COLORS.items():
        fig.add_bar(x=mrr["month"], y=mrr[col] / 1e6, name=LABELS[col], marker_color=color, row=1, col=1)
    fig.add_scatter(
        x=mrr["month"],
        y=mrr["total_mrr"] / 1e6,
        name="MRR",
        mode="lines+markers",
        line=dict(color="#1565C0", width=3),
        row=1,
        col=1,
        secondary_y=True,
    )
    fig.update_layout(barmode="relative")
    fig.update_yaxes(title_text="Изменение, млн ₽", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="MRR, млн ₽", row=1, col=1, secondary_y=True)

    # 2. Кривые удержания: средняя по всем когортам с размером не меньше 20 клиентов
    big = ret[ret["cohort_size"] >= 20]
    curve = big.groupby("month_number")["logo_retention"].mean()
    curve = curve[big.groupby("month_number")["cohort_month"].nunique() >= 3]  # точки с ≥3 когортами
    fig.add_scatter(
        x=curve.index, y=curve.values * 100, mode="lines+markers", name="Logo retention", line=dict(color="#6A1B9A"),
        row=2, col=1,
    )
    fig.update_xaxes(title_text="Месяцев с подключения", row=2, col=1)
    fig.update_yaxes(title_text="% клиентов", range=[0, 105], row=2, col=1)

    # 3. Липкость по продуктам
    eng = eng.sort_values("stickiness")
    fig.add_bar(
        x=eng["stickiness"] * 100, y=eng["product"], orientation="h", marker_color="#00897B",
        text=[f"{v:.0%}" for v in eng["stickiness"]], textposition="outside", showlegend=False, row=2, col=2,
    )
    fig.update_xaxes(title_text="DAU / MAU, %", row=2, col=2)

    # 4. Тепловая карта NRR по когортам
    pivot = ret.pivot(index="cohort_month", columns="month_number", values="revenue_retention") * 100
    fig.add_heatmap(
        z=pivot.values,
        x=pivot.columns,
        y=pivot.index.strftime("%Y-%m"),
        colorscale="RdYlGn",
        zmid=100,
        text=pivot.round(0).values,
        texttemplate="%{text}",
        colorbar=dict(title="NRR, %", len=0.35, y=0.17),
        row=3,
        col=1,
    )
    fig.update_xaxes(title_text="Месяцев с подключения", row=3, col=1)
    fig.update_yaxes(autorange="reversed", row=3, col=1)

    last = mrr.iloc[-1]
    fig.update_layout(
        title=(
            f"SaaS-метрики платформы · MRR {last['total_mrr'] / 1e6:.1f} млн ₽ · "
            f"ARR run rate {last['arr_run_rate'] / 1e6:.0f} млн ₽ · "
            f"отток клиентов {mrr['logo_churn_rate'].tail(6).mean():.1%} в месяц (6 мес.)"
        ),
        template="plotly_white",
        height=1500,
        legend=dict(orientation="h", y=1.04, x=0),
    )
    return fig


if __name__ == "__main__":
    out = REPORTS / "dashboard.html"
    build().write_html(out, include_plotlyjs="cdn")
    print(f"Дашборд сохранён: {out}")
