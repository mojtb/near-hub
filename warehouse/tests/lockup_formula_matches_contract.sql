-- The schedule formula in gold must give what each contract itself answers at a past block. A contract whose owner has not turned
-- transfers on answers its whole amount, which the formula deliberately counts as released, so those are held to that amount instead.
with schedules as (
    select *, {{ lockup_dates() }} from {{ ref('stg_rpc__lockups') }} where is_latest and lockup_amount_near is not null
),

compared as (
    select
        v.read_day,
        v.lockup_no,
        v.transfers_enabled,
        v.contract_locked_near,
        {{ lockup_locked_near('v.block_ns') }} as formula_near,
        lockup_amount_near - case when v.block_ns >= coalesce(finished_ns, 1e30) then last_withdrawn_near else first_withdrawn_near end as whole_amount_near
    from {{ ref('stg_rpc__lockup_contract_views') }} v
    join schedules using (lockup_no)
)

select *
from compared
where abs(contract_locked_near - case when transfers_enabled then formula_near else whole_amount_near end) > greatest(1.0, 0.0001 * contract_locked_near)
