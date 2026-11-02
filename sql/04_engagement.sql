-- Вовлечённость по продуктам за последние 28 дней данных:
--   avg_dau     — среднее число уникальных пользователей в рабочий день
--   mau_28d     — уникальные пользователи за 28 дней
--   stickiness  — avg_dau / mau_28d: насколько продукт стал ежедневной привычкой
--   share_of_users — доля всех активных пользователей платформы, которые пользуются продуктом

WITH
    (SELECT max(event_date) FROM saas.product_activity) AS last_day,
    (
        SELECT uniqExact(user_id)
        FROM saas.product_activity
        WHERE event_date > last_day - 28
    ) AS platform_mau

SELECT
    product,
    round(avg(dau), 1)                       AS avg_dau,
    any(mau)                                 AS mau_28d,
    round(avg(dau) / any(mau), 3)            AS stickiness,
    round(any(mau) / platform_mau, 3)        AS share_of_users
FROM
(
    SELECT
        product,
        event_date,
        uniqExact(user_id) AS dau
    FROM saas.product_activity
    WHERE event_date > last_day - 28 AND toDayOfWeek(event_date) <= 5
    GROUP BY product, event_date
) AS daily
INNER JOIN
(
    SELECT product, uniqExact(user_id) AS mau
    FROM saas.product_activity
    WHERE event_date > last_day - 28
    GROUP BY product
) AS monthly USING (product)
GROUP BY product
ORDER BY stickiness DESC;
