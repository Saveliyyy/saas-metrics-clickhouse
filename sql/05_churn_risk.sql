-- Точка роста: клиенты в зоне риска оттока.
-- Сравниваем недельную активность (WAU) последних 4 недель с предыдущими 4 неделями.
-- Падение больше чем на 30% при живой подписке — сигнал для customer success.

WITH
    weekly AS
    (
        SELECT
            account_id,
            toMonday(event_date)   AS week,
            uniqExact(user_id)     AS wau
        FROM saas.product_activity
        GROUP BY account_id, week
    ),

    ranked AS
    (
        SELECT
            account_id,
            week,
            wau,
            -- avg за 4 недели: текущая и три предыдущие
            avg(wau) OVER (PARTITION BY account_id ORDER BY week ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS wau_4w,
            -- avg за 4 недели до этого окна
            avg(wau) OVER (PARTITION BY account_id ORDER BY week ROWS BETWEEN 7 PRECEDING AND 4 PRECEDING) AS wau_prev_4w,
            row_number() OVER (PARTITION BY account_id ORDER BY week DESC) AS rn_desc,
            count() OVER (PARTITION BY account_id) AS weeks_observed
        FROM weekly
    ),

    last_billing AS
    (
        SELECT account_id, argMax(mrr, month) AS current_mrr, max(month) AS last_paid_month
        FROM saas.billing_monthly
        GROUP BY account_id
    )

SELECT
    account_id,
    a.size_segment,
    a.plan,
    lb.current_mrr,
    round(r.wau_prev_4w, 1)                       AS wau_prev_4w,
    round(r.wau_4w, 1)                            AS wau_last_4w,
    round(r.wau_4w / r.wau_prev_4w - 1, 3)        AS wau_change
FROM ranked AS r
INNER JOIN saas.accounts AS a USING (account_id)
INNER JOIN last_billing AS lb USING (account_id)
WHERE r.rn_desc = 1                                   -- последняя неделя
  AND r.weeks_observed >= 8                           -- есть с чем сравнить
  AND lb.last_paid_month = (SELECT max(month) FROM saas.billing_monthly)  -- клиент ещё платит
  AND r.wau_4w / r.wau_prev_4w - 1 < -0.3
ORDER BY lb.current_mrr DESC;
