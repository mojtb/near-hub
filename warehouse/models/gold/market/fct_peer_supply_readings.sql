-- Total supply of each chain's token on a day it was read, beside the supply its market cap counted on that day.
-- A peer's market cap counts what its project reports as circulating, so the share differs by chain and no two
-- caps are on one rule. Peers come from registry/peer_supply_readings.csv, each read once from the chain or from a
-- provider that indexes it. NEAR's total is this warehouse's own, from the block header (fct_supply_daily).
-- TON has no row: its total supply has not been read.
with readings as (
    select chain_id, reading_date, total_supply_tokens, read_from, evidence_level, note
    from {{ ref('peer_supply_readings') }}

    union all
    select 'near', d.reading_date, s.total_supply_near, 'Block header, in fct_supply_daily', 'read_from_chain', null
    from (select distinct reading_date from {{ ref('peer_supply_readings') }}) d
    join {{ ref('fct_supply_daily') }} s on s.date_day = d.reading_date
)

select
    r.chain_id,
    r.reading_date,
    r.total_supply_tokens,
    p.implied_supply_tokens as supply_behind_cap_tokens,
    p.implied_supply_tokens / r.total_supply_tokens as share_of_total_counted,
    r.read_from,
    r.evidence_level,
    r.note
from readings r
left join {{ ref('fct_peer_daily') }} p on p.chain_id = r.chain_id and p.date_day = r.reading_date
