-- Different service bundles can remain; review inclusions before interpreting these ranges.
select procedure_id, setting, billing_class, modifiers, price_type, payer_id, is_demo,
    count(distinct hospital_id) as hospital_count,
    min(amount) as minimum_price, max(amount) as maximum_price,
    median(amount) as median_price, max(amount) / nullif(min(amount), 0) as max_min_ratio
from {{ ref('fct_prices') }}
group by procedure_id, setting, billing_class, modifiers, price_type, payer_id, is_demo
having count(distinct hospital_id) >= 2
