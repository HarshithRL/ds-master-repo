WITH industry_orders AS (
  SELECT
    item.`Sales Document Number`,
    item.`Sales Document Item Number`,
    item.`Measure Net Value in Euro` AS order_value_eur,
    item.`Measure Sales Order Quantity` AS order_qty,
    item.`Delivery Date To Key`,
    item.`Plant Key`,
    COALESCE(csm.`cs_team`, 'Unmapped') AS cs_team,
    COALESCE(item.`Application area Description`, 'Unknown') AS segment,
    item.`Order Status` AS order_status
  FROM
    `${var.catalog}`.silver.`SC_BI_industry_sales_src_dbx_fact_sales_distribution_sales_document_item${var.source_snapshot_suffix}` item
      JOIN `${var.catalog}`.silver.`SC_BI_industry_sales_src_dbx_dim_sales_organization${var.source_snapshot_suffix}` sorg
        ON sorg.`Sales Organization Key` = item.`Sales Organization Key`
      LEFT JOIN ${var.catalog}.gold.${var.mapping_table_name} csm
        ON sorg.`Sales_Organization ID` = csm.`sales_org_code`
  WHERE
    sorg.`Business Unit 2` = '34'
    AND (
      item.`Rejection Status` != 'C'
      OR item.`Rejection Status` IS NULL
    )
    AND (
      item.`Sales Document Type Description` IN (
        'Standard Order', 'Rush Order', 'Consignment Issue'
      )
      OR item.`Sales Document Type` IN ('YOR', 'YSO', 'YKE', 'YKB')
    )
    AND item.`Created On` >= 20260101
    ),
all_confirmed_sl_raw AS (
  SELECT
    sl.`Sales Document Number`,
    sl.`Sales Document Item Number`,
    TO_DATE(CAST(sl.`Goods Issue Date` AS STRING), 'yyyyMMdd') AS gi_date,
    sl.`Measure Confirmed Quantity` AS confirmed_qty,
    sl.`Measure Order Quantity` AS sl_oq
  FROM
    `${var.catalog}`.silver.`SC_BI_industry_sales_src_dbx_fact_sales_distribution_schedule_line${var.source_snapshot_suffix}` sl
      INNER JOIN industry_orders io
        ON sl.`Sales Document Number` = io.`Sales Document Number`
        AND sl.`Sales Document Item Number` = io.`Sales Document Item Number`
  WHERE
    sl.`Measure Confirmed Quantity` > 0
    AND sl.`Goods Issue Date`
      >= 20260101
),
all_confirmed_sl AS (
  SELECT `Sales Document Number`, `Sales Document Item Number`, gi_date, confirmed_qty
  FROM (
    SELECT r.*,
      MAX(CASE WHEN r.sl_oq > 0 THEN 1 ELSE 0 END)
        OVER (PARTITION BY r.`Sales Document Number`, r.`Sales Document Item Number`) AS has_oq
    FROM all_confirmed_sl_raw r
  )
  WHERE sl_oq > 0 OR has_oq = 0
),
all_unconfirmed_sl AS (
  SELECT
    sl.`Sales Document Number`,
    sl.`Sales Document Item Number`,
    TO_DATE(CAST(sl.`Goods Issue Date` AS STRING), 'yyyyMMdd') AS gi_date,
    sl.`Measure Order Quantity` AS sl_order_qty
  FROM
    `${var.catalog}`.silver.`SC_BI_industry_sales_src_dbx_fact_sales_distribution_schedule_line${var.source_snapshot_suffix}` sl
      INNER JOIN industry_orders io
        ON sl.`Sales Document Number` = io.`Sales Document Number`
        AND sl.`Sales Document Item Number` = io.`Sales Document Item Number`
  WHERE
    sl.`Measure Confirmed Quantity` = 0
    AND sl.`Measure Order Quantity` > 0
    AND sl.`Goods Issue Date`
      >= CAST(DATE_FORMAT(DATE_TRUNC('YEAR', CURRENT_DATE()), 'yyyyMMdd') AS INT)
),
item_confirmed_total AS (
  SELECT
    `Sales Document Number`,
    `Sales Document Item Number`,
    SUM(confirmed_qty) AS total_confirmed
  FROM
    all_confirmed_sl
  GROUP BY
    `Sales Document Number`,
    `Sales Document Item Number`
),
item_unconfirmed_total AS (
  SELECT
    `Sales Document Number`,
    `Sales Document Item Number`,
    SUM(sl_order_qty) AS total_unconfirmed
  FROM
    all_unconfirmed_sl
  GROUP BY
    `Sales Document Number`,
    `Sales Document Item Number`
),
items_with_any_sl AS (
  SELECT
    `Sales Document Number`,
    `Sales Document Item Number`
  FROM
    all_confirmed_sl
  WHERE
    gi_date >= DATE_TRUNC('YEAR', CURRENT_DATE())
  UNION
  SELECT
    `Sales Document Number`,
    `Sales Document Item Number`
  FROM
    all_unconfirmed_sl
),
rule1a AS (
  SELECT
    CASE
      WHEN
        s.gi_date BETWEEN DATE_TRUNC('MONTH', CURRENT_DATE()) AND LAST_DAY(CURRENT_DATE())
      THEN
        'CM'
      WHEN
        s.gi_date >= DATE_TRUNC('YEAR', CURRENT_DATE())
        AND s.gi_date < DATE_TRUNC('MONTH', CURRENT_DATE())
      THEN
        'YTD'
      WHEN s.gi_date > LAST_DAY(CURRENT_DATE()) THEN 'FUT'
      ELSE 'PRE'
    END AS scope,
    s.gi_date AS delivery_date,
    CASE
      WHEN
        ict.total_confirmed >= io.order_qty
        OR io.order_qty = 0
      THEN
        io.order_value_eur * (s.confirmed_qty / ict.total_confirmed)
      ELSE io.order_value_eur * (s.confirmed_qty / GREATEST(io.order_qty, ict.total_confirmed))
    END AS allocated_value,
    io.order_qty,
    io.`Sales Document Number`,
    io.`Sales Document Item Number`,
    io.`Plant Key`,
    io.cs_team,
    io.segment,
    s.confirmed_qty AS line_qty,
    io.order_status
  FROM
    industry_orders io
      JOIN item_confirmed_total ict
        ON ict.`Sales Document Number` = io.`Sales Document Number`
        AND ict.`Sales Document Item Number` = io.`Sales Document Item Number`
      JOIN all_confirmed_sl s
        ON s.`Sales Document Number` = io.`Sales Document Number`
        AND s.`Sales Document Item Number` = io.`Sales Document Item Number`
),
rule1b_partial AS (
  SELECT
    CASE
      WHEN
        s.gi_date BETWEEN DATE_TRUNC('MONTH', CURRENT_DATE()) AND LAST_DAY(CURRENT_DATE())
      THEN
        'CM'
      WHEN
        s.gi_date >= DATE_TRUNC('YEAR', CURRENT_DATE())
        AND s.gi_date < DATE_TRUNC('MONTH', CURRENT_DATE())
      THEN
        'YTD'
      WHEN s.gi_date > LAST_DAY(CURRENT_DATE()) THEN 'FUT'
    END AS scope,
    s.gi_date AS delivery_date,
    io.order_value_eur
      * (1.0 - LEAST(ict.total_confirmed / GREATEST(io.order_qty, 1), 1.0))
      * (s.sl_order_qty / iut.total_unconfirmed) AS allocated_value,
    io.order_qty,
    io.`Sales Document Number`,
    io.`Sales Document Item Number`,
    io.`Plant Key`,
    io.cs_team,
    io.segment,
    s.sl_order_qty AS line_qty,
    io.order_status
  FROM
    industry_orders io
      JOIN item_confirmed_total ict
        ON ict.`Sales Document Number` = io.`Sales Document Number`
        AND ict.`Sales Document Item Number` = io.`Sales Document Item Number`
      JOIN item_unconfirmed_total iut
        ON iut.`Sales Document Number` = io.`Sales Document Number`
        AND iut.`Sales Document Item Number` = io.`Sales Document Item Number`
      JOIN all_unconfirmed_sl s
        ON s.`Sales Document Number` = io.`Sales Document Number`
        AND s.`Sales Document Item Number` = io.`Sales Document Item Number`
  WHERE
    ict.total_confirmed < io.order_qty
    AND io.order_qty > 0
),
rule1b_full AS (
  SELECT
    CASE
      WHEN
        s.gi_date BETWEEN DATE_TRUNC('MONTH', CURRENT_DATE()) AND LAST_DAY(CURRENT_DATE())
      THEN
        'CM'
      WHEN
        s.gi_date >= DATE_TRUNC('YEAR', CURRENT_DATE())
        AND s.gi_date < DATE_TRUNC('MONTH', CURRENT_DATE())
      THEN
        'YTD'
      WHEN s.gi_date > LAST_DAY(CURRENT_DATE()) THEN 'FUT'
    END AS scope,
    s.gi_date AS delivery_date,
    io.order_value_eur * (s.sl_order_qty / iut.total_unconfirmed) AS allocated_value,
    io.order_qty,
    io.`Sales Document Number`,
    io.`Sales Document Item Number`,
    io.`Plant Key`,
    io.cs_team,
    io.segment,
    s.sl_order_qty AS line_qty,
    io.order_status
  FROM
    industry_orders io
      LEFT JOIN item_confirmed_total ict
        ON ict.`Sales Document Number` = io.`Sales Document Number`
        AND ict.`Sales Document Item Number` = io.`Sales Document Item Number`
      JOIN item_unconfirmed_total iut
        ON iut.`Sales Document Number` = io.`Sales Document Number`
        AND iut.`Sales Document Item Number` = io.`Sales Document Item Number`
      JOIN all_unconfirmed_sl s
        ON s.`Sales Document Number` = io.`Sales Document Number`
        AND s.`Sales Document Item Number` = io.`Sales Document Item Number`
  WHERE
    ict.`Sales Document Number` IS NULL
),
rule2 AS (
  SELECT
    CASE
      WHEN
        dd.dim_date BETWEEN DATE_TRUNC('MONTH', CURRENT_DATE()) AND LAST_DAY(CURRENT_DATE())
      THEN
        'CM'
      WHEN
        dd.dim_date >= DATE_TRUNC('YEAR', CURRENT_DATE())
        AND dd.dim_date < DATE_TRUNC('MONTH', CURRENT_DATE())
      THEN
        'YTD'
      WHEN dd.dim_date > LAST_DAY(CURRENT_DATE()) THEN 'FUT'
    END AS scope,
    dd.dim_date AS delivery_date,
    io.order_value_eur AS allocated_value,
    io.order_qty,
    io.`Sales Document Number`,
    io.`Sales Document Item Number`,
    io.`Plant Key`,
    io.cs_team,
    io.segment,
    io.order_qty AS line_qty,
    io.order_status
  FROM
    industry_orders io
      LEFT JOIN items_with_any_sl isl
        ON isl.`Sales Document Number` = io.`Sales Document Number`
        AND isl.`Sales Document Item Number` = io.`Sales Document Item Number`
      JOIN (
        SELECT
          `Date Delivery Key`,
          `Date Delivery` AS dim_date
        FROM
          `${var.catalog}`.silver.`SC_BI_industry_sales_src_dbx_date_delivery${var.source_snapshot_suffix}`
      ) dd
        ON dd.`Date Delivery Key` = io.`Delivery Date To Key`
  WHERE
    isl.`Sales Document Number` IS NULL
    AND dd.dim_date >= DATE_TRUNC('YEAR', CURRENT_DATE())
),
all_alloc AS (
  SELECT
    *
  FROM
    rule1a
  WHERE
    scope IN ('CM', 'YTD', 'FUT')
  UNION ALL
  SELECT
    *
  FROM
    rule1b_partial
  WHERE
    scope IS NOT NULL
  UNION ALL
  SELECT
    *
  FROM
    rule1b_full
  WHERE
    scope IS NOT NULL
  UNION ALL
  SELECT
    *
  FROM
    rule2
  WHERE
    scope IS NOT NULL
),
orders_in_scope AS (
  SELECT DISTINCT
    `Sales Document Number`,
    `Sales Document Item Number`
  FROM
    all_alloc
),
billing AS (
  SELECT
    b.`Sales Document Number`,
    b.`Sales Document Item Number`,
    SUM(b.`Billed Quantity`) AS billed_qty
  FROM
    `${var.catalog}`.silver.`SC_BI_industry_sales_src_dbx_fact_billing_document_line_item${var.source_snapshot_suffix}` b
      INNER JOIN orders_in_scope ois
        ON ois.`Sales Document Number` = b.`Sales Document Number`
        AND ois.`Sales Document Item Number` = b.`Sales Document Item Number`
  WHERE
    b.`Billed Quantity` > 0
    AND b.`SD Document Category` = 'M'
  GROUP BY
    b.`Sales Document Number`,
    b.`Sales Document Item Number`
),
delivery_tbl AS (
  SELECT
    d.`Reference Document` AS `Sales Document Number`,
    d.`Reference Item` AS `Sales Document Item Number`,
    SUM(d.`Measure Actual Delivery Quantity`) AS delivered_qty
  FROM
    `${var.catalog}`.silver.`SC_BI_industry_sales_src_dbx_fact_sales_distribution_delivery_item${var.source_snapshot_suffix}` d
      INNER JOIN orders_in_scope ois
        ON ois.`Sales Document Number` = d.`Reference Document`
        AND ois.`Sales Document Item Number` = d.`Reference Item`
  WHERE
    d.`Goods Movement Status` = 'C'
  GROUP BY
    d.`Reference Document`,
    d.`Reference Item`
),
combined AS (
  SELECT
    a.scope,
    a.cs_team,
    a.segment,
    a.`Plant Key`,
    a.delivery_date,
    a.allocated_value,
    a.line_qty,
    a.order_status,
    COALESCE(b.billed_qty, 0) AS billed_qty,
    GREATEST(COALESCE(d.delivered_qty, 0), COALESCE(b.billed_qty, 0)) AS fulfilled_qty,
    SUM(a.line_qty) OVER (
        PARTITION BY a.`Sales Document Number`, a.`Sales Document Item Number`
        ORDER BY a.delivery_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
      ) AS cumul_qty
  FROM
    all_alloc a
      LEFT JOIN billing b
        ON b.`Sales Document Number` = a.`Sales Document Number`
        AND b.`Sales Document Item Number` = a.`Sales Document Item Number`
      LEFT JOIN delivery_tbl d
        ON d.`Sales Document Number` = a.`Sales Document Number`
        AND d.`Sales Document Item Number` = a.`Sales Document Item Number`
),
bucketed AS (
  SELECT
    scope,
    cs_team,
    segment,
    `Plant Key`,
    delivery_date,
    allocated_value,
    CASE
      WHEN
        line_qty > 0
      THEN
        allocated_value
          * LEAST(
            GREATEST(LEAST(billed_qty, cumul_qty) - (cumul_qty - line_qty), 0) / line_qty,
            1.0
          )
      ELSE
        CASE
          WHEN fulfilled_qty > 0 THEN allocated_value
          ELSE 0
        END
    END AS billed_value,
    CASE
      WHEN
        line_qty > 0
      THEN
        GREATEST(
          allocated_value
            * LEAST(
              GREATEST(LEAST(fulfilled_qty, cumul_qty) - (cumul_qty - line_qty), 0) / line_qty,
              1.0
            )
            - allocated_value
              * LEAST(
                GREATEST(LEAST(billed_qty, cumul_qty) - (cumul_qty - line_qty), 0) / line_qty,
                1.0
              ),
          0
        )
      ELSE 0
    END AS delivered_not_billed_value,
    CASE
      WHEN
        line_qty > 0
      THEN
        allocated_value
          * (
            1
              - LEAST(
                GREATEST(LEAST(fulfilled_qty, cumul_qty) - (cumul_qty - line_qty), 0) / line_qty,
                1.0
              )
          )
      ELSE
        CASE
          WHEN fulfilled_qty > 0 THEN 0
          ELSE allocated_value
        END
    END
      * CASE
        WHEN order_status = 'C' THEN 0
        ELSE 1
      END AS open_value
  FROM
    combined
),
agg AS (
  SELECT
    scope,
    cs_team,
    segment,
    `Plant Key`,
    ROUND(SUM(GREATEST(billed_value, 0)), 0) AS billed_eur,
    ROUND(SUM(GREATEST(delivered_not_billed_value, 0)), 0) AS delivered_not_billed_eur,
    ROUND(
      SUM(
        CASE
          WHEN delivery_date < DATE_SUB(CURRENT_DATE(), 1) THEN GREATEST(open_value, 0)
          ELSE 0
        END
      ),
      0
    ) AS open_past_due_eur,
    ROUND(
      SUM(
        CASE
          WHEN delivery_date >= DATE_SUB(CURRENT_DATE(), 1) THEN GREATEST(open_value, 0)
          ELSE 0
        END
      ),
      0
    ) AS open_not_yet_due_eur,
    ROUND(SUM(allocated_value), 0) AS total_eur
  FROM
    bucketed
  GROUP BY
    scope,
    cs_team,
    segment,
    `Plant Key`
)
SELECT
  a.scope,
  a.cs_team,
  a.segment,
  COALESCE(p.`Plant Code & Text`, CAST(a.`Plant Key` AS STRING)) AS plant,
  b.bucket,
  b.value_eur
FROM
  agg a
    LEFT JOIN `${var.catalog}`.silver.`SC_BI_industry_sales_src_dbx_dim_plant${var.source_snapshot_suffix}` p
      ON p.`Plant Key` = a.`Plant Key`
  LATERAL VIEW
    STACK(
      4,
      'Billed',
      a.billed_eur,
      'Delivered (not billed)',
      a.delivered_not_billed_eur,
      'Open Past Due',
      a.open_past_due_eur,
      'Open Not Yet Due',
      a.open_not_yet_due_eur
    ) b
    AS bucket, value_eur