// The vocabulary the translator needs, read from the database itself (so it never names a
// DISCOM or a year the database does not hold).
export function vocabFrom(all, today = new Date()) {
  const discoms = all("SELECT code, name, state, commission, ownership, aliases FROM discoms").map((d) => ({ ...d, aliases: JSON.parse(d.aliases || "[]") }));
  const commissions = all("SELECT code, name, state FROM commissions");
  const states = [...new Set(commissions.map((c) => c.state))];
  // the latest ARR year an order approves, but never a year that has not begun
  const y = today.getUTCMonth() >= 3 ? today.getUTCFullYear() : today.getUTCFullYear() - 1;
  const current = `FY${y}-${String((y + 1) % 100).padStart(2, "0")}`;
  const latestYear = all(`SELECT MAX(arr_year) AS y FROM orders WHERE read_status = 'read' AND arr_year <= '${current}'`)[0].y;
  return { discoms, commissions, states, latestYear };
}
