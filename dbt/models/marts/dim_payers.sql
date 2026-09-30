select distinct payer_id, payer, plan from {{ ref('fct_prices') }}
