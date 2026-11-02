#!/usr/bin/env bash
# Полный прогон: схема → загрузка CSV → агрегаты → проверки → выгрузка результатов в reports/.
#
# По умолчанию работает с ClickHouse из docker-compose.
# Без Docker можно использовать clickhouse local:
#   CH="clickhouse local --path ./chdata" ./scripts/run_all.sh
set -euo pipefail
cd "$(dirname "$0")/.."

CH=${CH:-"docker compose exec -T clickhouse clickhouse-client"}
mkdir -p reports

echo "→ Схема"
$CH --multiquery < sql/01_schema.sql

echo "→ Загрузка данных"
$CH --query "TRUNCATE TABLE IF EXISTS saas.accounts"
$CH --query "TRUNCATE TABLE IF EXISTS saas.billing_monthly"
$CH --query "TRUNCATE TABLE IF EXISTS saas.product_activity"
$CH --query "INSERT INTO saas.accounts FORMAT CSVWithNames" < data/accounts.csv
$CH --query "INSERT INTO saas.billing_monthly FORMAT CSVWithNames" < data/billing_monthly.csv
$CH --query "INSERT INTO saas.product_activity FORMAT CSVWithNames" < data/product_activity.csv

echo "→ Агрегаты"
$CH --query "DROP TABLE IF EXISTS saas.mv_daily_product_usage"
$CH --query "DROP TABLE IF EXISTS saas.agg_daily_product_usage"
$CH --multiquery < sql/06_aggregates.sql

echo "→ Проверки"
$CH --multiquery --format TSV < sql/07_checks.sql | tee reports/checks.tsv
if grep -qP '\t0$' reports/checks.tsv; then echo "Проверка не пройдена" >&2; exit 1; fi

echo "→ Выгрузка метрик"
$CH --format CSVWithNames < sql/02_mrr_movements.sql   > reports/mrr_movements.csv
$CH --format CSVWithNames < sql/03_cohort_retention.sql > reports/cohort_retention.csv
$CH --format CSVWithNames < sql/04_engagement.sql      > reports/engagement.csv
$CH --format CSVWithNames < sql/05_churn_risk.sql      > reports/churn_risk.csv

echo "Готово: результаты в reports/"
