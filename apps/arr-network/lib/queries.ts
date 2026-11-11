// Queries shared by pages and the JSON API.
import type { Sql } from "./db.ts";

/** Orders that concern a state: through their utilities, or through the commission when an order lists none. */
export function stateOrders(sql: Sql, code: string) {
  return sql`
    SELECT o.order_id, o.commission, o.title, o.url, o.arr_year, o.kind, o.read_status, o.pages, o.pages_without_text, o.order_date,
           (SELECT string_agg(ou.utility, ', ' ORDER BY ou.utility) FROM order_utilities ou WHERE ou.order_id = o.order_id) AS utilities,
           (SELECT count(*) FROM facts f WHERE f.order_id = o.order_id)::int AS facts
    FROM orders o
    WHERE EXISTS (SELECT 1 FROM order_utilities ou JOIN utilities u ON u.code = ou.utility WHERE ou.order_id = o.order_id AND u.state = ${code})
       OR (NOT EXISTS (SELECT 1 FROM order_utilities ou WHERE ou.order_id = o.order_id)
           AND o.commission IN (SELECT commission FROM commission_states WHERE state = ${code}))
    ORDER BY o.arr_year DESC NULLS LAST, o.commission, o.order_id`;
}

export function utilityOrders(sql: Sql, code: string) {
  return sql`
    SELECT o.order_id, o.commission, o.title, o.url, o.arr_year, o.kind, o.read_status, o.pages, o.order_date,
           (SELECT count(*) FROM facts f WHERE f.order_id = o.order_id AND f.utility = ${code})::int AS facts
    FROM orders o JOIN order_utilities ou ON ou.order_id = o.order_id
    WHERE ou.utility = ${code}
    ORDER BY o.arr_year DESC NULLS LAST, o.order_id`;
}

export function stateCoverage(sql: Sql, code: string) {
  return sql`SELECT c.utility, c.name, c.kind, c.commission, c.orders::int, c.orders_read::int, c.years_with_arr::int,
                    c.latest_approved_year, u.ownership
             FROM v_coverage c JOIN utilities u ON u.code = c.utility
             WHERE c.state = ${code} ORDER BY c.kind, c.utility`;
}

/** ARR by year for one utility: the latest claim, the first approval, and the latest word. */
export function utilityArr(sql: Sql, code: string) {
  return sql`
    WITH years AS (SELECT DISTINCT fiscal_year FROM v_arr WHERE utility = ${code}),
    claimed AS (SELECT * FROM v_arr_latest WHERE utility = ${code} AND voice = 'claimed'),
    latest AS (SELECT * FROM v_arr_latest WHERE utility = ${code} AND voice = 'approved'),
    first_approval AS (
      SELECT DISTINCT ON (fiscal_year) * FROM v_arr
      WHERE utility = ${code} AND voice = 'approved' AND order_arr_year = fiscal_year
      ORDER BY fiscal_year, fact_id DESC)
    SELECT y.fiscal_year,
           c.value_crore AS claimed_crore, c.fact_id AS claimed_fact, c.consensus AS claimed_consensus, c.reviewed_by AS claimed_reviewed_by,
           c.page AS claimed_page, c.order_url AS claimed_url, c.order_id AS claimed_order,
           a.value_crore AS approved_crore, a.fact_id AS approved_fact, a.consensus AS approved_consensus, a.reviewed_by AS approved_reviewed_by,
           a.page AS approved_page, a.order_url AS approved_url, a.order_id AS approved_order,
           l.value_crore AS latest_crore, l.fact_id AS latest_fact, l.consensus AS latest_consensus, l.reviewed_by AS latest_reviewed_by,
           l.page AS latest_page, l.order_url AS latest_url, l.order_id AS latest_order, l.stage AS latest_stage, l.order_arr_year AS latest_order_year,
           l.label AS latest_label
    FROM years y
    LEFT JOIN claimed c ON c.fiscal_year = y.fiscal_year
    LEFT JOIN first_approval a ON a.fiscal_year = y.fiscal_year
    LEFT JOIN latest l ON l.fiscal_year = y.fiscal_year
    ORDER BY y.fiscal_year`;
}
