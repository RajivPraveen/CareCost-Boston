select * from {{ ref('stg_validated_prices') }} where rejection_reason is not null
