-- Supply per stablecoin per chain, as of each DefiLlama reading. Peer chains are included for comparison.
select snapshot_date, p.chain_id, s.symbol, s.asset_name, s.peg_type, s.circulating
from {{ ref('stg_defillama__stablecoin_assets') }} s
join {{ ref('peers') }} p on p.llama_chain = s.llama_chain
