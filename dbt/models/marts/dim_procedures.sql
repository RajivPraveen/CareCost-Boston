with codes as (
    select procedure_id, code, code_type, min(description) as description
    from {{ ref('fct_prices') }}
    group by procedure_id, code, code_type
)
select c.*, coalesce(l.plain_language_name, c.description) as plain_language_name,
    coalesce(l.category, 'Uncategorized') as category
from codes c left join {{ ref('procedure_labels') }} l using (procedure_id)
