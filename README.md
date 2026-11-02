# Продуктовые метрики B2B SaaS в ClickHouse

Расчёт ключевых метрик подписочного бизнеса для платформы из четырёх продуктов (почта, календарь, ВКС, мессенджер): MRR и его декомпозиция, ARR run rate, когортное удержание клиентов и выручки, вовлечённость по продуктам, поиск клиентов в зоне риска оттока.

## Стек

ClickHouse (MergeTree, AggregatingMergeTree, материализованные представления, оконные функции) · Python (pandas, NumPy) · Plotly · Docker

## Что считается

| Файл | Метрики | Что показывает из SQL |
| --- | --- | --- |
| `sql/02_mrr_movements.sql` | MRR, ARR run rate, new / expansion / contraction / churned MRR, logo churn rate | `lagInFrame`, `row_number`, `UNION ALL` для генерации месяца оттока, `sumIf` / `countIf` |
| `sql/03_cohort_retention.sql` | Logo retention и NRR по когортам месяца подключения | `dateDiff`, `first_value` по окну |
| `sql/04_engagement.sql` | DAU, MAU, stickiness (DAU/MAU), доля пользователей продукта | скалярные подзапросы в `WITH`, `uniqExact` |
| `sql/05_churn_risk.sql` | Клиенты с падением WAU > 30% за 4 недели | скользящие окна `ROWS BETWEEN 7 PRECEDING AND 4 PRECEDING`, `argMax` |
| `sql/06_aggregates.sql` | Дневной агрегат по продуктам и клиентам | `AggregatingMergeTree`, `uniqState` / `sumState`, materialized view |
| `sql/07_checks.sql` | Сходимость MRR-моста, агрегата и сырых данных, дубли, «сироты» | проверки качества данных |

`src/crosscheck.py` независимо пересчитывает MRR и когорты в pandas и сверяет с ClickHouse.

## Ключевые выводы (на синтетических данных)

- **MRR 23,9 млн ₽, ARR run rate 287 млн ₽** на конец июня 2026, рост в основном за счёт новых клиентов
- **Отток ~3,3% клиентов в месяц**, к 12-му месяцу остаётся ~59% когорты
- **NRR когорт ниже 100%** (95% на 3-м месяце, 88% на 12-м): расширение лицензий не компенсирует отток. Это главная точка роста
- **ВКС — самый слабый продукт**: им пользуются 38% пользователей, липкость 17% против 54% у почты. Гипотеза: встроить запуск звонка в календарь и мессенджер
- **23 клиента в зоне риска** (активность упала больше чем на 30%) несут **6,4% MRR**. Их стоит передать в customer success до продления

## Запуск

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python src/generate_data.py          # синтетические данные в data/
docker compose up -d                 # ClickHouse
./scripts/run_all.sh                 # схема → загрузка → агрегаты → проверки → выгрузка в reports/
python src/crosscheck.py             # сверка SQL с pandas
python src/dashboard.py              # reports/dashboard.html
```

Без Docker подойдёт `clickhouse local`: `CH="clickhouse local --path ./chdata" ./scripts/run_all.sh`.

## Модель данных

- `accounts` — клиент, месяц подключения, сегмент, тариф, отрасль
- `billing_monthly` — ежемесячное начисление: лицензии × цена = MRR
- `product_activity` — пользователь × день × продукт, число событий

Данные синтетические (`src/generate_data.py`). В них заложены отток, который у крупных клиентов ниже, расширение и сокращение лицензий, разная вовлечённость по продуктам и затухание активности перед уходом клиента.
