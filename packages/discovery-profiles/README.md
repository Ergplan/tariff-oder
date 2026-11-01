# Discovery profiles

How the library finds the official URL of each order on a commission's website (ADR-0019,
increment 32).  One JSON file per commission, `<commission>.v<version>.json`; data, not code.

A profile lists the commission's **listing pages** and how to page through them:

- `static` — a plain page; every PDF link on it is a proposal.
- `aspnet_year_select` — an ASP.NET WebForms page with a financial-year drop-down: optionally
  one postback to open the year filter (`open_event`), then for each requested year select it
  in `year_field` (formatted by `year_format`: `{start}` 2025, `{end2}` 26, `{end4}` 2026;
  with a postback when `year_postback`), then press `submit_name`.  Hidden fields
  (`__VIEWSTATE`, `__EVENTVALIDATION`) are carried as a browser would; disabled inputs and empty
  drop-downs are not posted.

`licensee_groups` maps a phrase a title uses for several licensees ("State Discoms") to their
codes; an order for a group is proposed once per licensee.  A listing's `licensee` names the
one licensee (a code) or the group (a key of `licensee_groups`) whose orders it lists: a title
naming none is proposed for it, or for each of the group (MPERC, OERC).

A link that shows no words (an icon, "View") takes its title from its table row; when the
table's header groups columns ("Tariff Order" over Date | Download, "True Up Order" over its
own), from the group above the link and the row's single-column cells ("Period").

Discovery only **proposes**: each proposal says what it guessed (kind, year, licensee, the
years and voices the title says the order decides) and why; a person confirms proposals
before they are recorded, and acquisition is a separate job.  Nothing found on a website is a
fact.  Status `draft` means the profile was written against the site on the date given and
has not been checked by the operator.
