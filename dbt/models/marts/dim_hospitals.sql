select hospital_id, payload:name::varchar as name,
    payload:latitude::float as latitude, payload:longitude::float as longitude,
    payload:city::varchar as city, payload:health_system::varchar as health_system,
    payload
from {{ source('raw', 'hospital_records') }}
