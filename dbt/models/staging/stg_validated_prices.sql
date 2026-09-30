with checked as (
    select p.*,
        case
            when p.price_id is null then 'missing_price_id'
            when p.code is null or not regexp_like(p.code, '([0-9]{5}|[A-Z][0-9]{4}|[0-9]{4}[A-Z])') then 'invalid_code'
            when p.code_type is null or p.code_type not in ('CPT', 'HCPCS') then 'unsupported_code_type'
            when p.amount is null or p.amount <= 0 or p.amount > 1000000 then 'invalid_amount'
            when p.source_date is null or p.source_date > current_date then 'invalid_source_date'
            when coalesce(p.source_url, '') = '' or coalesce(p.source_sha256, '') = '' then 'missing_lineage'
            when p.source_row is null or p.source_row < 1 then 'invalid_source_row'
            when p.service_id is null or p.description is null then 'missing_service'
            when p.price_type is null or p.price_type not in ('gross', 'cash', 'negotiated') then 'invalid_price_type'
            when p.setting is null or p.setting not in ('inpatient', 'outpatient', 'both') then 'invalid_setting'
            when p.billing_class is null or p.billing_class not in ('facility', 'professional', 'both', 'unknown') then 'invalid_class'
            when p.price_type = 'negotiated' and (coalesce(p.payer, '') = '' or coalesce(p.plan, '') = '') then 'missing_payer_plan'
            when p.price_type != 'negotiated' and (coalesce(p.payer, '') != '' or coalesce(p.plan, '') != '') then 'unexpected_payer_plan'
            when h.hospital_id is null then 'missing_hospital'
            when count(*) over (partition by p.price_id) > 1 then 'duplicate_price_id'
        end as rejection_reason
    from {{ ref('stg_prices') }} p
    left join {{ source('raw', 'hospital_records') }} h on p.hospital_id = h.hospital_id
)
select * from checked
