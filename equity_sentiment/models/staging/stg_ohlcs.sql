select 
    o.*
from {{ source('raw_ohlcs', 'ohlcs') }} o
inner join {{ ref('stg_companies') }} c
    on o.ticker = c.ticker