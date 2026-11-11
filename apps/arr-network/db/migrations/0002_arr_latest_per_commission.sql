-- v_arr_latest kept one row per (utility, fiscal_year, voice).  State totals are all stored
-- under utility 'TOTAL', so the totals of different states collapsed into one row nationally.
-- Partition by commission as well: a real utility has one commission, so its rows are unchanged;
-- each commission's TOTAL now keeps its own latest word.  Same columns, same order.
CREATE OR REPLACE VIEW v_arr_latest AS
SELECT DISTINCT ON (utility, commission, fiscal_year, voice) *
FROM v_arr
ORDER BY utility, commission, fiscal_year, voice, order_arr_year DESC NULLS LAST, fact_id DESC;
