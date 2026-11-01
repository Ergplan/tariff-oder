/**
 * The atlas's shapes (the API's /atlas, /atlas/states/{code}, /atlas/licensees/{code} and
 * /arr/norms/{commission}) and the tile map of India.  A tile map, not boundaries: one equal tile
 * per state or union territory in its approximate place, so that small states are as easy to
 * click as large ones and no boundary is drawn (official boundaries need the Survey of India's).
 */

export type AtlasState = {
  code: string;
  name: string;
  kind: string;
  fixture: boolean;
  commissions: { code: string; name: string; licensees: number }[];
  licensees: number;
  documents: number;
  documents_located: number;
  orders_reading: number;
  reviewed_facts: number;
};
export type Atlas = { states: AtlasState[]; note: string };

export type Licensee = {
  code: string;
  name: string;
  kind: string;
  dataset: string | null;
  documents: number;
  documents_located: number;
  orders_reading: number;
  reviewed_facts: number;
  latest_reviewed_year: string | null;
};
export type StateDetail = {
  code: string;
  name: string;
  kind: string;
  commissions: { code: string; name: string; commission_documents: number; licensees: Licensee[] }[];
};
export type LicenseePlace = Licensee & { commission: string; commission_name: string; state: string; state_name: string };

type Noted = { value: string | null; note: string | null };
export type Norms = {
  commission: string;
  commission_name: string;
  plan: { id: string; version: number; status: string };
  plan_confirmed: boolean;
  mapping: { id: string; version: number; status: string };
  mapping_confirmed: boolean;
  regulations: { role: string; title: string; year: number | null; control_periods: Record<string, string | null>[]; amendments: string[]; note: string | null }[];
  regulations_in_library: { title: string | null; fiscal_year: string | null; kind: string; url: string | null; level: string; source_id: string | null }[];
  conventions: {
    return_basis: Noted;
    gap_convention: Noted;
    loss_basis: Noted;
    total_includes: { total: string; includes: string[]; note?: string | null }[];
    decided_by_reviewer: { key: string; value: string; note: string | null; by: string | null }[];
  };
  base_rule: { prefer: string[]; note: string | null };
  lines: { line_code: string; label: string; method: string; method_words: string; parameters: { key: string; words: string }[]; unit: string; note: string | null }[];
  applied: { licensee: string; line_code: string; fiscal_year: string; voice: string; value: string; unit: string | null; order: string; page: number | null; source_id: string; is_fixture: boolean }[];
  note: string;
};

// [column, row, short label] on a 9 x 7 grid, north at the top
export const TILES: Record<string, [number, number, string]> = {
  JKL: [3, 0, "J&K·LA"],
  PB: [2, 1, "PB"],
  HP: [3, 1, "HP"],
  UK: [4, 1, "UK"],
  RJ: [1, 2, "RJ"],
  HR: [2, 2, "HR"],
  DL: [3, 2, "DL"],
  UP: [4, 2, "UP"],
  BR: [5, 2, "BR"],
  SK: [6, 2, "SK"],
  AR: [8, 2, "AR"],
  GJ: [1, 3, "GJ"],
  MP: [2, 3, "MP"],
  CG: [3, 3, "CG"],
  JH: [4, 3, "JH"],
  WB: [5, 3, "WB"],
  AS: [7, 3, "AS"],
  NL: [8, 3, "NL"],
  MH: [2, 4, "MH"],
  TG: [3, 4, "TG"],
  OD: [4, 4, "OD"],
  ML: [7, 4, "ML"],
  MNMZ: [8, 4, "MN·MZ"],
  GOAUT: [1, 5, "GOA"],
  KA: [2, 5, "KA"],
  AP: [3, 5, "AP"],
  TR: [7, 5, "TR"],
  KL: [2, 6, "KL"],
  TN: [3, 6, "TN"],
};

export function status(s: Pick<AtlasState, "reviewed_facts" | "orders_reading" | "documents_located">): "facts" | "reading" | "located" | "none" {
  if (s.reviewed_facts > 0) return "facts";
  if (s.orders_reading > 0) return "reading";
  if (s.documents_located > 0) return "located";
  return "none";
}

export const STATUS_WORDS: Record<string, string> = {
  facts: "Reviewed ARR facts",
  reading: "Orders being read",
  located: "Documents located",
  none: "Nothing on record yet",
};

export const CONVENTION_WORDS: Record<string, string> = {
  before_subsidy: "before the State Government's subsidy",
  after_subsidy: "after the State Government's subsidy",
  sales_within_state: "on sales within the state (inter-state sales excluded)",
  retail_sales: "on all retail sales",
  applies: "applies",
  does_not_apply: "does not apply",
};
