"""Discovery profiles (increment 32): the ASP.NET year-select engine against a local server
that behaves like a WebForms listing (view state, event validation that refuses what a
browser would not post), and the proposals made from what it lists.  SYNTHETIC titles."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest

from tariff_api.discovery import Fetcher, Listing, Profile, form_fields, load_profile, run, year_value

DOCS = {
    "2025-2026": [
        (
            "SYN-A Tariff Order for True-up for FY 2023-24, APR for 2024-25 and ARR and Tariff for FY 2025-26 in Petition no 11/2024",
            "App_File/SYNA_TO-pdf1.pdf",
        ),
        (
            "Scanned Order - SYN-A Tariff Order for True-up for FY 2023-24, APR for 2024-25 and ARR and Tariff for FY 2025-26 in Petition no 11/2024",
            "App_File/SYNA_TO_scan-pdf2.pdf",
        ),
        (
            "Synthetic Discoms Tariff Order dated 01/09/25 for True-up for FY 2023-24, APR for 2024-25 and ARR and Tariff for FY 2025-26 (Digitally Signed)",
            "App_File/SYND_TO-pdf3.pdf",
        ),
        ("Corrigendum dated 05/09/25 to the Tariff Order of SYN-A for FY 2025-26", "App_File/SYNA_corr-pdf4.pdf"),
        ("Order dated 01/08/25 in the matter of Appeal No. 9 of 2021", "App_File/appeal-pdf5.pdf"),
    ],
    "2024-2025": [
        (
            "SYN-A Tariff Order for True-up for FY 2022-23, APR for 2023-24 and ARR and Tariff for FY 2024-25",
            "App_File/SYNA_TO24-pdf6.pdf",
        ),
    ],
}
CURRENT = [("SYN-A Tariff Order for ARR and Tariff for FY 2026-27", "App_File/SYNA_TO27-pdf7.pdf")]
DISABLED = "ctl00$Main$txtFrom"


def _page(state: str, rows: list[tuple[str, str]], *, years: bool, selected: str = "") -> bytes:
    sel = ' selected="selected"'
    opts = "".join(
        f'<option value="{y}"{sel if y == selected else ""}>{y}</option>'
        for y in ("2026-2027", "2025-2026", "2024-2025", "2023-2024")
    )
    body = "".join(
        f"<tr><td>{i + 1}</td><td>{t}</td><td><a class='aaa' href={h}>{h.rsplit('/', 1)[-1]}</a></td></tr>"
        for i, (t, h) in enumerate(rows)
    )
    year_controls = (
        f'<select name="ctl00$Main$ddlFYear" onchange="x">{opts}</select>'
        '<input type="submit" name="ctl00$Main$btnShow" value="Show" />'
    )
    return f"""<html><body><form name="aspnetForm" method="post" action="./Orders.aspx" id="aspnetForm">
<input type="hidden" name="__VIEWSTATE" value="{state}" /><input type="hidden" name="__EVENTVALIDATION" value="ev-{state}" />
<input name="{DISABLED}" type="text" value="01/11/2026" disabled="disabled" />
<select name="ctl00$Main$ddlPetitionNo"></select>
{year_controls if years else ""}
<a href="javascript:__doPostBack('ctl00$Main$btnPrev','')">Previous Years</a>
<table>{body}</table></form></body></html>""".encode()


class _Handler(BaseHTTPRequestHandler):
    posts: list[dict[str, list[str]]] = []

    def log_message(self, *a):  # quiet
        pass

    def _send(self, body: bytes, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        self._send(_page("v0", CURRENT, years=False))

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("content-length") or 0)
        form = parse_qs(self.rfile.read(n).decode(), keep_blank_values=True)
        type(self).posts.append(form)
        one = {k: v[0] for k, v in form.items()}
        # what a browser never posts makes WebForms refuse the request
        if DISABLED in one or "ctl00$Main$ddlPetitionNo" in one or "__VIEWSTATE" not in one:
            return self._send(b"Server Error in '/' Application. Invalid postback or callback argument.", 500)
        target = one.get("__EVENTTARGET", "")
        if target == "ctl00$Main$btnPrev" and one["__VIEWSTATE"] == "v0":
            return self._send(_page("v1", CURRENT, years=True))
        fy = one.get("ctl00$Main$ddlFYear", "")
        if target == "ctl00$Main$ddlFYear" and one["__VIEWSTATE"] == "v1":
            return self._send(_page("v2", CURRENT, years=True, selected=fy))
        if one.get("ctl00$Main$btnShow") == "Show" and one["__VIEWSTATE"] == "v2":
            return self._send(_page("v3", DOCS.get(fy, []), years=True, selected=fy))
        return self._send(b"Server Error in '/' Application.", 500)


@pytest.fixture()
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.posts = []
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _profile(base: str) -> Profile:
    return Profile(
        id="synth-discovery",
        version=1,
        commission="SYNTHERC",
        status="test",
        licensee_groups={"Synthetic Discoms": ["SYN-B", "SYN-C"]},
        listings=[
            Listing(
                name="Tariff orders",
                url=f"{base}/Orders.aspx",
                method="aspnet_year_select",
                open_event="ctl00$Main$btnPrev",
                year_field="ctl00$Main$ddlFYear",
                submit_name="ctl00$Main$btnShow",
                submit_value="Show",
            )
        ],
    )


def test_form_fields_post_what_a_browser_posts():
    page = _page("v1", [], years=True, selected="2024-2025").decode()
    f = form_fields(page)
    assert f["__VIEWSTATE"] == "v1" and f["ctl00$Main$ddlFYear"] == "2024-2025"
    assert DISABLED not in f and "ctl00$Main$ddlPetitionNo" not in f and "ctl00$Main$btnShow" not in f
    assert year_value("FY2025-26", "{start}-{end4}") == "2025-2026"
    assert year_value("FY2025-26", "FY {start}-{end2}") == "FY 2025-26"


def test_year_select_listing_pages_through_and_proposes(server):
    lic = {"SYN-A": ["SYNTHETIC licensee A"], "SYN-B": [], "SYN-C": []}
    out = run(
        _profile(server),
        ["FY2025-26", "FY2024-25", "FY2019-20"],
        licensees=lic,
        fetcher=Fetcher(pause=0),
    )
    pages = {p["fiscal_year"]: p for p in out["pages"]}
    assert pages["FY2025-26"]["documents"] == 6 and pages["FY2025-26"]["error"] is None
    assert pages["FY2024-25"]["documents"] == 1
    assert "offers no year '2019-2020'" in pages["FY2019-20"]["error"]
    # one GET, the 'previous years' postback, then select + show per offered year
    assert out["requests"] == 6
    assert all("ctl00$Main$txtFrom" not in p for p in _Handler.posts)

    props = out["proposals"]
    by = {(p["url"].rsplit("/", 1)[-1], p["utility_code"]): p for p in props}
    to = by[("SYNA_TO-pdf1.pdf", "SYN-A")]
    assert to["title"].startswith("SYN-A Tariff Order")  # the row's description, not the file name
    assert (to["document_kind"], to["fiscal_year"], to["preferred"], to["complete"]) == (
        "tariff_order",
        "FY2025-26",
        True,
        True,
    )
    assert to["decides"] == [
        {"fy": "FY2023-24", "value_type": "final_true_up"},
        {"fy": "FY2024-25", "value_type": "provisional_true_up"},
        {"fy": "FY2025-26", "value_type": "approved"},
    ]
    assert to["listing"] == "Tariff orders FY2025-26" and to["url"].startswith(server + "/App_File/")
    scan = by[("SYNA_TO_scan-pdf2.pdf", "SYN-A")]
    assert scan["variant"] == "scanned" and not scan["preferred"] and not scan["complete"]
    # an order for a group of licensees is proposed once for each
    for code in ("SYN-B", "SYN-C"):
        g = by[("SYND_TO-pdf3.pdf", code)]
        assert g["variant"] == "digitally_signed" and g["complete"] and g["fiscal_year"] == "FY2025-26"
    corr = by[("SYNA_corr-pdf4.pdf", "SYN-A")]
    assert corr["document_kind"] is None and "corrigendum" in corr["notes"][0]
    appeal = next(p for p in props if p["url"].endswith("appeal-pdf5.pdf"))
    assert appeal["document_kind"] is None and not appeal["complete"]


def test_a_refused_post_is_reported_not_raised(server):
    p = _profile(server)
    p.listings[0].open_event = "ctl00$Main$nothing"
    out = run(p, ["FY2025-26"], licensees={}, fetcher=Fetcher(pause=0))
    assert out["proposals"] == [] and "refused the form post" in out["pages"][0]["error"]


def test_the_uperc_profile_loads():
    p = load_profile("UPERC")
    assert p is not None and p.listings[0].method == "aspnet_year_select"
    assert set(p.licensee_groups["State Discoms"]) == {"PVVNL", "PUVVNL", "MVVNL", "DVVNL", "KESCO"}
    assert load_profile("NOSUCH") is None
