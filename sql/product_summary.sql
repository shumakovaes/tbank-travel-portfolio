-- SQLite. orders содержит только проверенные AIR/HOT-заказы.
-- Цена успешных бронирований не является выручкой банка.
SELECT order_type_cd AS product,
       COUNT(*) AS orders,
       SUM(is_success) AS successful_orders,
       SUM(CASE WHEN is_success = 1 AND valid_amount = 1
                THEN nominal_price_rub_amt END) AS successful_booking_value_rub
FROM orders
GROUP BY order_type_cd
ORDER BY order_type_cd;
