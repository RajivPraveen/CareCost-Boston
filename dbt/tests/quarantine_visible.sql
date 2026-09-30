{{ config(severity='warn') }}
select * from {{ ref('quarantined_prices') }}
