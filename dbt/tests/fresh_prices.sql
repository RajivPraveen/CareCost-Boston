{{ config(severity='warn') }}
select * from {{ ref('fct_prices') }} where datediff('day', source_date, current_date) > 366
