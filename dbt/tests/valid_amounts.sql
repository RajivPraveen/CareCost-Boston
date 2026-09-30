select * from {{ ref('fct_prices') }} where amount <= 0 or amount > 1000000
