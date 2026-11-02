-- Схема хранилища: сырые таблицы на движке MergeTree.
-- ORDER BY подобран под типичные фильтры: по продукту и дате для активности, по месяцу для биллинга.

CREATE DATABASE IF NOT EXISTS saas;

CREATE TABLE IF NOT EXISTS saas.accounts
(
    account_id     UInt32,
    signup_month   Date,
    size_segment   LowCardinality(String),
    plan           LowCardinality(String),
    industry       LowCardinality(String),
    initial_seats  UInt32
)
ENGINE = MergeTree
ORDER BY account_id;

CREATE TABLE IF NOT EXISTS saas.billing_monthly
(
    account_id      UInt32,
    month           Date,
    seats           UInt32,
    price_per_seat  UInt32,
    mrr             UInt64
)
ENGINE = MergeTree
PARTITION BY toYear(month)
ORDER BY (month, account_id);

CREATE TABLE IF NOT EXISTS saas.product_activity
(
    event_date  Date,
    account_id  UInt32,
    user_id     UInt64,
    product     LowCardinality(String),
    events      UInt32
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_date)
ORDER BY (product, event_date, account_id, user_id);
