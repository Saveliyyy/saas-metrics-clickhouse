-- Когортный анализ по месяцу подключения клиента.
--   logo_retention    — доля клиентов когорты, которые всё ещё платят через N месяцев
--   revenue_retention — MRR когорты через N месяцев / MRR когорты в первый месяц (NRR когорты).
--                       Может быть > 100%, если оставшиеся клиенты докупают лицензии.

WITH
    cohorts AS
    (
        SELECT account_id, min(month) AS cohort_month
        FROM saas.billing_monthly
        GROUP BY account_id
    ),

    cohort_activity AS
    (
        SELECT
            c.cohort_month,
            dateDiff('month', c.cohort_month, b.month) AS month_number,
            count()        AS active_accounts,
            sum(b.mrr)     AS cohort_mrr
        FROM saas.billing_monthly AS b
        INNER JOIN cohorts AS c USING (account_id)
        GROUP BY c.cohort_month, month_number
    )

SELECT
    cohort_month,
    month_number,
    active_accounts,
    cohort_mrr,
    first_value(active_accounts) OVER w                          AS cohort_size,
    round(active_accounts / first_value(active_accounts) OVER w, 4) AS logo_retention,
    round(cohort_mrr / first_value(cohort_mrr) OVER w, 4)           AS revenue_retention
FROM cohort_activity
WINDOW w AS (PARTITION BY cohort_month ORDER BY month_number ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
ORDER BY cohort_month, month_number;
