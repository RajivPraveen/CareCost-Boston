select * exclude (rejection_reason)
from {{ ref('stg_validated_prices') }}
where rejection_reason is null
