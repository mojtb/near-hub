{# NEAR locked in one lockup contract at time t (nanoseconds, as a double), from the columns of stg_rpc__lockups plus
   lockup_start_ns and release_end_ns. This is the formula NEAR Explorer used, near/core-contracts getters.rs with one change:
   every lockup counts transfers as enabled from the moment the network did, even if its owner never told the contract, because
   those tokens only wait on the owner's call. A termination has three stages: the schedule until changed_ns; from then until
   finished_ns the contract locks the unvested amount it fixed at the start; after that the newest state applies. #}
{% macro lockup_locked_near(t) -%}
    case
        when {{ t }} < created_ns or {{ t }} >= coalesce(gone_ns, 1e30) then 0.0
        when {{ t }} < lockup_start_ns then
            lockup_amount_near - case when {{ t }} >= coalesce(finished_ns, 1e30) then last_withdrawn_near else first_withdrawn_near end
        else greatest(
            greatest(
                case
                    when release_duration_ns is null or {{ t }} >= release_end_ns then 0.0
                    else lockup_amount_near * (release_end_ns - {{ t }}) / release_duration_ns
                end - case when {{ t }} >= coalesce(finished_ns, 1e30) then last_withdrawn_near else first_withdrawn_near end,
                0.0
            ),
            case
                when {{ t }} >= coalesce(finished_ns, 1e30) then case when last_vesting_kind = 'terminating' then last_unvested_near else 0.0 end
                when {{ t }} >= coalesce(changed_ns, 1e30) then terminating_unvested_near
                when first_vesting_kind = 'terminating' then first_unvested_near
                when first_vesting_kind = 'schedule' then
                    case
                        when {{ t }} < vesting_cliff_ns then lockup_amount_near
                        when {{ t }} >= vesting_end_ns then 0.0
                        else lockup_amount_near * (vesting_end_ns - {{ t }}) / (vesting_end_ns - vesting_start_ns)
                    end
                else 0.0
            end
        )
    end
{%- endmacro %}


{# A lockup's fixed dates. An early contract version (https://github.com/near/core-contracts/pull/136) measured its release from
   the day transfers were enabled and not from the end of the lockup, so it ends sooner. NEAR Explorer named the versions below. #}
{% macro lockup_dates() -%}
    greatest(1602614338293769340.0 + lockup_duration_ns, coalesce(lockup_timestamp_ns, 0)) as lockup_start_ns,
    case
        when code_hash in ('3kVY9qcVRoW3B5498SMX6R3rtSLiCdmBzKs7zcnzDJ7Q', 'DiC9bKCqUHqoYqUXovAnqugiuntHWnM3cAc7KrgaHTu')
            then 1602614338293769340.0 + release_duration_ns
        else greatest(1602614338293769340.0 + lockup_duration_ns, coalesce(lockup_timestamp_ns, 0)) + release_duration_ns
    end as release_end_ns
{%- endmacro %}
