select
    n.*
from {{ source('raw_news', 'news') }} n
inner join {{ ref('stg_companies') }} c
    on n.ticker = c.ticker