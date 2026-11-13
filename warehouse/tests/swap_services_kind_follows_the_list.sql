-- What a figure counts follows from the DefiLlama list it is read from, so registry/swap_services.csv may not name one
-- kind and ask another list: `dexs` with dailyVolume is swap_volume, `bridges` with dailyOutgoingVolume is bridge_volume.
-- Exactly one row names no list, and that row is NEAR Intents, whose series is this warehouse's own.
select service_id, llama_dimension, llama_data_type, figure_kind, 'kind does not follow the list' as fault
from {{ ref('swap_services') }}
where llama_slug is not null
    and (llama_dimension, llama_data_type, figure_kind) not in (
        ('dexs', 'dailyVolume', 'swap_volume'),
        ('bridges', 'dailyOutgoingVolume', 'bridge_volume')
    )

union all

select service_id, llama_dimension, llama_data_type, figure_kind, 'a row without a slug must name no list or id' as fault
from {{ ref('swap_services') }}
where llama_slug is null and (llama_dimension is not null or llama_id is not null or llama_data_type is not null)

union all

select string_agg(service_id, ', '), null, null, null, 'exactly one row may name no list' as fault
from {{ ref('swap_services') }}
where llama_slug is null
having count(*) <> 1
