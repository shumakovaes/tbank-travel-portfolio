SELECT substr(created_dttm, 1, 7) AS month,
       order_type_cd AS product,
       COUNT(*) AS orders,
       SUM(is_success) AS successful_orders
FROM orders
GROUP BY substr(created_dttm, 1, 7), order_type_cd
ORDER BY month, product;
