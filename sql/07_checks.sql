-- Проверки качества данных и сходимости расчётов. Каждый запрос должен вернуть 0 строк
-- или значение ok = 1.

-- 1. MRR сходится: MRR(t) - MRR(t-1) = new + expansion + contraction + churned
WITH movements AS
(
    SELECT
        month,
        total_mrr,
        new_mrr + expansion_mrr + contraction_mrr + churned_mrr AS net_change,
        lagInFrame(total_mrr, 1, 0) OVER (ORDER BY month ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) AS prev_total
    FROM
    (
        WITH
            (SELECT max(month) FROM saas.billing_monthly) AS last_month,
            base AS
            (
                SELECT account_id, month, toInt64(mrr) AS mrr FROM saas.billing_monthly
                UNION ALL
                SELECT account_id, churn_month, toInt64(0)
                FROM (SELECT account_id, addMonths(max(month), 1) AS churn_month FROM saas.billing_monthly GROUP BY account_id)
                WHERE churn_month <= last_month
            ),
            with_prev AS
            (
                SELECT account_id, month, mrr,
                       lagInFrame(mrr, 1, 0) OVER w AS prev_mrr,
                       row_number() OVER w AS rn
                FROM base
                WINDOW w AS (PARTITION BY account_id ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
            )
        SELECT
            month,
            sum(mrr)                                                     AS total_mrr,
            sumIf(mrr, rn = 1)                                           AS new_mrr,
            sumIf(mrr - prev_mrr, rn > 1 AND mrr > prev_mrr)             AS expansion_mrr,
            sumIf(mrr - prev_mrr, rn > 1 AND mrr < prev_mrr AND mrr > 0) AS contraction_mrr,
            -sumIf(prev_mrr, rn > 1 AND mrr = 0)                         AS churned_mrr
        FROM with_prev
        GROUP BY month
    )
)
SELECT 'mrr_bridge' AS check_name, min(total_mrr - prev_total = net_change) AS ok FROM movements;

-- 2. Агрегат совпадает с сырыми данными по числу событий
SELECT
    'aggregate_events' AS check_name,
    (SELECT sum(events) FROM saas.product_activity)
        = (SELECT sumMerge(events) FROM saas.agg_daily_product_usage) AS ok;

-- 3. Нет дублей (клиент, месяц) в биллинге
SELECT 'billing_duplicates' AS check_name, count() = 0 AS ok
FROM (SELECT account_id, month FROM saas.billing_monthly GROUP BY account_id, month HAVING count() > 1);

-- 4. Активность есть только у известных клиентов
SELECT 'orphan_activity' AS check_name, count() = 0 AS ok
FROM saas.product_activity
WHERE account_id NOT IN (SELECT account_id FROM saas.accounts);
