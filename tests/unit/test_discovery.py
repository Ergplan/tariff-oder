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


STATIC = {
    "/list": """<html><body>
      <ul class="menu"><li><a href="/uploads/act.pdf">Electricity Act 2003</a></li></ul>
      <table>
        <tr><td>1</td><td>Determination of Aggregate Revenue Requirement and Tariff for FY 2026-27 &amp; Final True-up for the 4th MYT Control Period</td><td><a href="/uploads/to2627.pdf">to2627.pdf</a></td></tr>
        <tr><td>2</td><td>Press Release of the Tariff Order for FY 2026-27</td><td><a href="/uploads/press.pdf">press.pdf</a></td></tr>
        <tr><td>3</td><td>Approval for True-up of FY 2024-25 for EDS</td><td><a href="/uploads/tu2425.pdf">Download</a></td></tr>
        <tr><td>4</td><td>Tariff Order for FY 2012-13</td><td><a href="/uploads/to1213.pdf">to1213.pdf</a></td></tr>
        <tr><td>5</td><td>Review order seeking review of the order dated 28.03.2025</td><td><a href="/uploads/rev.pdf">rev.pdf</a></td></tr>
        <tr><td>6</td><td>Order on Business Plan and Multi Year Tariff for FY 2026-27 to FY 2030-31</td><td><a href="/uploads/myt.pdf">myt.pdf</a></td></tr>
      </table></body></html>""",
    "/orders": """<html><body><table>
        <tr><td><a href="/orders/101-tariff-order-fy-2026-27">Tariff Order of DISCOMS (SYN-B &amp; SYN-C) for FY 2026-27</a></td></tr>
        <tr><td><a href="/orders/102-tariff-chart-fy-2026-27">Tariff Chart of SYN-B &amp; SYN-C for FY 2026-27</a></td></tr>
        <tr><td><a href="/about">About</a></td></tr>
      </table></body></html>""",
    "/orders/101-tariff-order-fy-2026-27": """<iframe src="/viewer/web/viewer.html?file=https://site.example/images/pdf/TO_2627.pdf"></iframe>""",
    "/orders/102-tariff-chart-fy-2026-27": """<a href="/images/pdf/chart_2627.pdf">chart</a>""",
}


class _Static(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):  # noqa: N802
        body = STATIC.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("content-type", "text/html")
        self.end_headers()
        self.wfile.write((body or "not found").encode())


@pytest.fixture()
def static_server():
    httpd = HTTPServer(("127.0.0.1", 0), _Static)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_static_listing_rows_only_licensee_from_page_aliases_and_year_floor(static_server):
    prof = Profile(
        id="t",
        version=1,
        commission="SYNTHERC",
        status="test",
        licensee_aliases={"SYN-S": ["EDS"]},
        listings=[
            Listing(
                name="One licensee's orders",
                url=f"{static_server}/list",
                method="static",
                rows_only=True,
                licensee="SYN-A",
            )
        ],
    )
    out = run(
        prof, ["FY2024-25", "FY2025-26", "FY2026-27"], licensees={"SYN-A": [], "SYN-S": []}, fetcher=Fetcher(pause=0)
    )
    by = {p["url"].rsplit("/", 1)[-1]: p for p in out["proposals"]}
    assert "act.pdf" not in by  # the site menu, not the table
    assert "to1213.pdf" not in by  # every year it names is before the years asked
    to = by["to2627.pdf"]
    # an annual order that mentions its control period is the annual order
    assert (to["document_kind"], to["fiscal_year"], to["utility_code"], to["complete"]) == (
        "tariff_order",
        "FY2026-27",
        "SYN-A",
        True,
    )
    assert "taken from the listing page" in " ".join(to["notes"])
    assert by["press.pdf"]["document_kind"] is None and "press release" in by["press.pdf"]["notes"][0]
    tu = by["tu2425.pdf"]  # "Approval for ..." is an order; the alias names the licensee
    assert (tu["document_kind"], tu["fiscal_year"], tu["utility_code"]) == ("arr_true_up_order", "FY2024-25", "SYN-S")
    assert by["rev.pdf"]["document_kind"] is None and "review" in by["rev.pdf"]["notes"][0]
    myt = by["myt.pdf"]
    assert (myt["document_kind"], myt["fiscal_year"]) == ("myt_order", "")
    assert "control period FY2026-27 to FY2030-31" in " ".join(myt["notes"])


def test_static_listing_follows_order_pages_to_their_pdfs(static_server):
    prof = Profile(
        id="t",
        version=1,
        commission="SYNTHERC",
        status="test",
        listings=[Listing(name="Orders", url=f"{static_server}/orders", method="static", follow=r"^/orders/\d+-")],
    )
    out = run(prof, ["FY2026-27"], licensees={"SYN-B": [], "SYN-C": []}, fetcher=Fetcher(pause=0))
    assert out["requests"] == 3  # the list and the two order pages; /about is not followed
    props = out["proposals"]
    order = [p for p in props if p["url"] == "https://site.example/images/pdf/TO_2627.pdf"]
    # the PDF inside the viewer link, with the list's title; one order for two licensees
    assert {p["utility_code"] for p in order} == {"SYN-B", "SYN-C"}
    assert all(p["complete"] and p["title"].startswith("Tariff Order of DISCOMS") for p in order)
    chart = [p for p in props if p["url"].endswith("chart_2627.pdf")]
    assert chart and all(p["document_kind"] is None for p in chart)


def test_every_profile_in_the_package_loads():
    from tariff_api.discovery import profile_commissions

    codes = profile_commissions()
    assert {"UPERC", "BERC", "HPERC", "JSERC", "JERC-GOA-UT"} <= set(codes)
    for c in codes:
        p = load_profile(c)
        assert p is not None and p.commission == c and p.status.startswith("draft")
