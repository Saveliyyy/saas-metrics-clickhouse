-- MRR, ARR run rate и декомпозиция изменения MRR по месяцам:
--   new          — первый платёж клиента
--   expansion    — клиент докупил лицензии (MRR вырос)
--   contraction  — клиент сократил лицензии, но остался
--   churned      — клиент перестал платить
-- Алиасы не совпадают с именами колонок: иначе ClickHouse подставит sum(mrr) внутрь других агрегатов.
-- Проверка: MRR(t) = MRR(t-1) + new + expansion + contraction + churned (см. 06_checks.sql).

WITH
    (SELECT max(month) FROM saas.billing_monthly) AS last_month,

    base AS
    (
        SELECT account_id, month, toInt64(mrr) AS mrr
        FROM saas.billing_monthly

        UNION ALL

        -- Месяц после последнего платежа — месяц оттока, MRR = 0.
        -- Для клиентов, плативших в последнем месяце данных, отток ещё не наступил.
        SELECT account_id, churn_month AS month, toInt64(0) AS mrr
        FROM
        (
            SELECT account_id, addMonths(max(month), 1) AS churn_month
            FROM saas.billing_monthly
            GROUP BY account_id
        )
        WHERE churn_month <= last_month
    ),

    with_prev AS
    (
        SELECT
            account_id,
            month,
            mrr,
            lagInFrame(mrr, 1, 0) OVER w AS prev_mrr,
            row_number() OVER w AS rn
        FROM base
        WINDOW w AS (PARTITION BY account_id ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    )

SELECT
    month,
    sum(mrr)                                                        AS total_mrr,
    sum(mrr) * 12                                                   AS arr_run_rate,
    sumIf(mrr, rn = 1)                                              AS new_mrr,
    sumIf(mrr - prev_mrr, rn > 1 AND mrr > prev_mrr)                AS expansion_mrr,
    sumIf(mrr - prev_mrr, rn > 1 AND mrr < prev_mrr AND mrr > 0)    AS contraction_mrr,
    -sumIf(prev_mrr, rn > 1 AND mrr = 0)                            AS churned_mrr,
    countIf(mrr > 0)                                                AS paying_accounts,
    countIf(rn = 1)                                                 AS new_accounts,
    countIf(mrr = 0)                                                AS churned_accounts,
    round(countIf(mrr = 0) / greatest(countIf(rn > 1), 1), 4)       AS logo_churn_rate
FROM with_prev
GROUP BY month
ORDER BY month;
