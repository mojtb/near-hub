{# NearBlocks lists a token under the chain its contract is on. Bitcoin bridged to NEAR lives in a NEAR contract, so
   NearBlocks lists it under near, while NEAR's own Intents dashboard counts it as Bitcoin. From 2026-05-06 almost all
   Bitcoin swaps run through this token, so leaving it under near would take Bitcoin out of the public chain split and
   put it into NEAR's. These are the token ids that gold counts as Bitcoin. #}
{% macro bridged_bitcoin_tokens() -%}
    'nep141:nbtc.bridge.near'
{%- endmacro %}
