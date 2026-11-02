-- Агрегат для дашбордов: дневная активность по продукту и клиенту.
-- AggregatingMergeTree хранит промежуточные состояния (uniqState, sumState),
-- поэтому из дневного агрегата можно честно посчитать уникальных пользователей
-- за неделю или месяц, без повторного прохода по сырым событиям.
-- Материализованное представление дополняет агрегат при каждой вставке в сырую таблицу.

CREATE TABLE IF NOT EXISTS saas.agg_daily_product_usage
(
    event_date  Date,
    product     LowCardinality(String),
    account_id  UInt32,
    users       AggregateFunction(uniq, UInt64),
    events      AggregateFunction(sum, UInt32)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(event_date)
ORDER BY (product, event_date, account_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS saas.mv_daily_product_usage
TO saas.agg_daily_product_usage
AS
SELECT
    event_date,
    product,
    account_id,
    uniqState(user_id) AS users,
    sumState(events)   AS events
FROM saas.product_activity
GROUP BY event_date, product, account_id;

-- Первичное наполнение агрегата историческими данными
-- (MV ловит только новые вставки, поэтому историю досыпаем вручную один раз).
INSERT INTO saas.agg_daily_product_usage
SELECT
    event_date,
    product,
    account_id,
    uniqState(user_id),
    sumState(events)
FROM saas.product_activity
GROUP BY event_date, product, account_id;
