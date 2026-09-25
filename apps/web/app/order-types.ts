/** What an instrument is (ARR spec section 5) and the voices a year can be decided in. */
export const ORDER_TYPE_LABEL: Record<string, string> = {
  tariff_order: "Tariff order (ARR, true-up and retail tariff)",
  arr_true_up_order: "ARR / true-up order (no tariff schedule)",
  myt_order: "Multi-year tariff (control period) order",
  mid_term_review: "Mid-term review of a control period",
  regulation: "Tariff regulations",
  regulation_amendment: "Amendment to tariff regulations",
  other: "Other instrument",
};
export const VALUE_TYPE_LABEL: Record<string, string> = {
  petitioned: "petitioned",
  approved: "approved",
  provisional_true_up: "provisional true-up",
  final_true_up: "final true-up",
  actual: "actual",
  control_period: "control-period year",
};
/** "FY2024-25:final_true_up, FY2026-27:approved" → list; throws on a malformed item. */
export function parseDecides(text: string): { fiscal_year: string; value_type: string }[] {
  return text
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean)
    .map((part) => {
      const [fy, vt] = part.split(":").map((x) => x.trim());
      if (!/^FY\d{4}-\d{2}$/.test(fy ?? "") || !(vt! in VALUE_TYPE_LABEL)) throw new Error(`cannot read "${part}": use FY2026-27:approved`);
      return { fiscal_year: fy!, value_type: vt! };
    });
}
export function decidesWords(list: { fiscal_year: string; value_type: string }[] | null | undefined): string {
  return (list ?? []).map((d) => `${d.fiscal_year} ${VALUE_TYPE_LABEL[d.value_type] ?? d.value_type}`).join(", ");
}
