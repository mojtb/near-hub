-- One row per bronze file, from data/bronze/_manifest/. Every number can be traced to a URL and a hash from here.
select
    source,
    dataset,
    key,
    snapshot as snapshot_date,
    path,
    url,
    fetched_at,
    sha256,
    bytes,
    rows,
    note
from read_json('data/bronze/_manifest/dt=*.jsonl', format = 'newline_delimited', columns = {
    source: 'VARCHAR', dataset: 'VARCHAR', key: 'VARCHAR', snapshot: 'DATE', path: 'VARCHAR', url: 'VARCHAR',
    fetched_at: 'VARCHAR', sha256: 'VARCHAR', bytes: 'BIGINT', rows: 'BIGINT', note: 'VARCHAR'
})
where snapshot <= cast('{{ var("as_of") }}' as date)
