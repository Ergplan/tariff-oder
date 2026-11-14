// The five sections of an order read by the Section Reader (tools/arrnet/arrnet/sections.py).
export const SECTIONS = [
  { key: "power_purchase", name: "Power purchase", short: "Power purchase",
    about: "Station- and source-wise power purchase quantum and cost, bulk supply tariff, average power purchase cost — claimed and approved." },
  { key: "re_portfolio", name: "Renewable energy portfolio", short: "Renewables",
    about: "Renewable purchase / consumption obligations (RPO, RCO), compliance, the renewable sources' cost and green tariff." },
  { key: "tariff_schedule", name: "Tariff schedule in detail", short: "Tariff schedule",
    about: "The retail tariff schedule, category by category as the commission names them (LMV-1 … HV-4 in Uttar Pradesh, LV-1 … HV-9 in Madhya Pradesh, DS / NDS / IAS / LTIS / HTS in Bihar and Jharkhand, RTS-1 … RTS-9 in Uttarakhand …): fixed / demand and energy charges by slab and supply voltage, miscellaneous charges and the category-wise billing rates." },
  { key: "wheeling", name: "Wheeling, transmission & open access", short: "Wheeling & OA",
    about: "Wheeling and retail supply split, wheeling charges, transmission charges, voltage-wise losses and cost of supply, cross-subsidy and additional surcharges." },
  { key: "tod", name: "Time of day (TOD)", short: "TOD",
    about: "Time-of-day slots and the rebate or surcharge on energy charges in each, per category and season." },
] as const;

export type SectionKey = (typeof SECTIONS)[number]["key"];
export const SECTION_KEYS: string[] = SECTIONS.map((s) => s.key);
