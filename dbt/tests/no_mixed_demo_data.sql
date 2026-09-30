select count(distinct is_demo) as kinds from {{ ref('fct_prices') }} having kinds > 1
