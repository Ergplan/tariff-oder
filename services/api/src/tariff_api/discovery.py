"""Commission discovery profiles (ADR-0019, increment 32): how the library pages through a
commission's listing pages to find the official URL of each order.  Profiles are data
(``packages/discovery-profiles``); this module is the engine that follows them — plain pages,
and ASP.NET WebForms pages with a financial-year drop-down — and hands each listing page to
``library.propose_from_html``.  It proposes; it records nothing and fetches no document."""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import time
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, ConfigDict, Field

USER_AGENT = "tariff-order-studio/1 (library discovery; one request at a time)"
_ASPNET_ERROR = re.compile(r"Invalid postback or callback argument|Server Error in '/' Application", re.I)


class Listing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    url: str
    method: Literal["static", "aspnet_year_select"]
    open_event: str | None = None
    year_field: str | None = None
    year_format: str = "{start}-{end4}"
    year_postback: bool = True
    submit_name: str | None = None
    submit_value: str | None = None
    listing_year_note: str | None = None
    # static listings: more pages ("{url}?start={offset}", offset = n x page_step), detail
    # pages to follow when the list links to a page per order rather than to the PDF, and a
    # pattern every proposed PDF URL must match (to leave navigation links out)
    page_template: str | None = None
    page_step: int = 0
    pages: int = Field(default=1, ge=1, le=20)
    follow: str | None = None
    max_follow: int = Field(default=40, ge=1, le=200)
    url_pattern: str | None = None
    rows_only: bool = False  # only PDFs inside table rows (site menus link PDFs too)
    licensee: str | None = None  # the listing is one licensee's: a title naming none is for it


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int = Field(ge=1)
    commission: str
    status: str
    note: str | None = None
    licensee_groups: dict[str, list[str]] = Field(default_factory=dict)
    # names the site uses for a licensee that the registry does not ("EDG" for GOA-ED)
    licensee_aliases: dict[str, list[str]] = Field(default_factory=dict)
    listings: list[Listing]


def profiles_dir() -> Path:
    env = os.environ.get("DISCOVERY_PROFILES_DIR")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "packages" / "discovery-profiles"
        if candidate.is_dir():
            return candidate
    return Path("packages/discovery-profiles")


@lru_cache(maxsize=32)
def load_profile(commission: str) -> Profile | None:
    """The latest profile of a commission, or None."""
    files = []
    for p in profiles_dir().glob(f"{commission.lower()}.v*.json"):
        m = re.fullmatch(rf"{re.escape(commission.lower())}\.v(\d+)\.json", p.name)
        if m:
            files.append((int(m.group(1)), p))
    if not files:
        return None
    return Profile.model_validate(json.loads(max(files)[1].read_text()))


def profile_commissions() -> list[str]:
    return sorted(
        {
            m.group(1).upper()
            for p in profiles_dir().glob("*.v*.json")
            if (m := re.fullmatch(r"(.+)\.v\d+\.json", p.name))
        }
    )


# ------------------------------------------------------------------ ASP.NET WebForms


def form_fields(page: str) -> dict[str, str]:
    """What a browser would post from the page's form: hidden and text inputs with their
    values, checked boxes, the selected option of each drop-down.  Disabled inputs, image and
    submit buttons, and drop-downs with no options are left out, as a browser leaves them."""
    out: dict[str, str] = {}
    for m in re.finditer(r"<input\b[^>]*>", page, re.I):
        tag = m.group(0)
        name = re.search(r'name\s*=\s*"([^"]+)"', tag)
        if not name or re.search(r"\bdisabled\b", tag, re.I):
            continue
        typ = (re.search(r'type\s*=\s*"([^"]+)"', tag, re.I) or [None, "text"])[1].lower()
        if typ in ("image", "submit", "button", "reset", "file"):
            continue
        if typ in ("checkbox", "radio") and not re.search(r"\bchecked\b", tag, re.I):
            continue
        value = re.search(r'value\s*=\s*"([^"]*)"', tag)
        out[html_lib.unescape(name.group(1))] = (
            html_lib.unescape(value.group(1)) if value else ("on" if typ in ("checkbox", "radio") else "")
        )
    for m in re.finditer(r"<select\b([^>]*)>(.*?)</select>", page, re.I | re.S):
        name = re.search(r'name\s*=\s*"([^"]+)"', m.group(1))
        if not name or re.search(r"\bdisabled\b", m.group(1), re.I):
            continue
        options = re.findall(r"<option\b([^>]*)>", m.group(2), re.I)
        if not options:
            continue
        chosen = next((o for o in options if re.search(r"\bselected\b", o, re.I)), options[0])
        value = re.search(r'value\s*=\s*"([^"]*)"', chosen)
        out[html_lib.unescape(name.group(1))] = html_lib.unescape(value.group(1)) if value else ""
    return out


def select_options(page: str, field: str) -> list[str]:
    m = re.search(rf'<select\b[^>]*name\s*=\s*"{re.escape(field)}"[^>]*>(.*?)</select>', page, re.I | re.S)
    if not m:
        return []
    return [html_lib.unescape(v) for v in re.findall(r'<option\b[^>]*value\s*=\s*"([^"]*)"', m.group(1), re.I)]


def _action(page: str, url: str) -> str:
    m = re.search(r'<form\b[^>]*action\s*=\s*"([^"]*)"', page, re.I)
    return urljoin(url, html_lib.unescape(m.group(1))) if m and m.group(1) else url


def year_value(fy: str, fmt: str) -> str:
    start = int(fy[2:6])
    return fmt.format(start=start, end2=f"{(start + 1) % 100:02d}", end4=start + 1)


class Fetcher:
    """One HTTP client, one request at a time, with a pause between requests."""

    def __init__(self, client: httpx.Client | None = None, *, pause: float = 1.0) -> None:
        self._own = client is None
        self.client = client or httpx.Client(
            follow_redirects=True, timeout=60, trust_env=True, headers={"User-Agent": USER_AGENT}
        )
        self.pause = pause
        self.requests = 0

    def _wait(self) -> None:
        if self.requests and self.pause:
            time.sleep(self.pause)
        self.requests += 1

    def get(self, url: str) -> tuple[str, str]:
        self._wait()
        r = self.client.get(url)
        if r.status_code != 200:
            raise DiscoveryError(f"{url} answered {r.status_code}")
        return r.text, str(r.url)

    def post(self, url: str, data: dict[str, str]) -> tuple[str, str]:
        self._wait()
        r = self.client.post(url, data=data)
        if r.status_code != 200 or _ASPNET_ERROR.search(r.text[:20000]):
            raise DiscoveryError(f"{url} refused the form post ({r.status_code})")
        return r.text, str(r.url)

    def close(self) -> None:
        if self._own:
            self.client.close()


class DiscoveryError(RuntimeError):
    pass


def postback(
    f: Fetcher,
    page: str,
    url: str,
    *,
    target: str = "",
    values: dict[str, str] | None = None,
    submit: tuple[str, str] | None = None,
) -> tuple[str, str]:
    data = form_fields(page)
    data.update(values or {})
    data["__EVENTTARGET"], data["__EVENTARGUMENT"] = target, ""
    if submit:
        data[submit[0]] = submit[1]
    return f.post(_action(page, url), data)


def fetch_listing(f: Fetcher, listing: Listing, fiscal_years: list[str]) -> list[dict[str, Any]]:
    """Each page of a listing, one per requested year for a year-select listing: name, year,
    url, html or the error that stopped it."""
    out: list[dict[str, Any]] = []
    try:
        page, url = f.get(listing.url)
    except (httpx.HTTPError, DiscoveryError) as e:
        return [{"listing": listing.name, "fiscal_year": "", "url": listing.url, "html": None, "error": _err(e)}]
    if listing.method == "static":
        return _static(f, listing, page, url)
    assert listing.year_field
    try:
        if listing.open_event:
            page, url = postback(f, page, url, target=listing.open_event)
    except (httpx.HTTPError, DiscoveryError) as e:
        return [{"listing": listing.name, "fiscal_year": "", "url": url, "html": None, "error": _err(e)}]
    offered = select_options(page, listing.year_field)
    for fy in fiscal_years:
        value = year_value(fy, listing.year_format)
        row: dict[str, Any] = {"listing": listing.name, "fiscal_year": fy, "url": url, "html": None, "error": None}
        if value not in offered:
            row["error"] = f"the site offers no year {value!r}"
            out.append(row)
            continue
        try:
            p2, u2 = page, url
            if listing.year_postback:
                p2, u2 = postback(f, page, url, target=listing.year_field, values={listing.year_field: value})
            submit = (listing.submit_name, listing.submit_value or "") if listing.submit_name else None
            p3, u3 = postback(f, p2, u2, values={listing.year_field: value}, submit=submit)
            row["html"], row["url"] = p3, u3
        except (httpx.HTTPError, DiscoveryError) as e:
            row["error"] = _err(e)
        out.append(row)
    return out


_ATTR_URL = re.compile(r"""(?:href|src|data)\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>"']+))""", re.I)
_A = re.compile(r"""<a\b[^>]*?href\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>"']+))[^>]*>(.*?)</a>""", re.I | re.S)


def pdf_links(page: str, url: str) -> list[str]:
    """Every PDF a page links or embeds, including a viewer's ``file=`` parameter."""
    out: list[str] = []
    for m in _ATTR_URL.finditer(page):
        v = html_lib.unescape(m.group(1) or m.group(2) or m.group(3) or "")
        inner = re.search(r"[?&]file=([^&#]+\.pdf)", v, re.I)
        v = inner.group(1) if inner else v
        if re.search(r"\.pdf(\?|#|$)", v, re.I):
            full = urljoin(url, v)
            if full not in out:
                out.append(full)
    return out


def _static(f: Fetcher, listing: Listing, page: str, url: str) -> list[dict[str, Any]]:
    """A plain listing, its further pages, and — when it links to a page per order — those
    pages followed for their PDFs.  The result is one page of rows (title, PDF link) for the
    proposer; ``url_pattern`` leaves out PDFs that are not orders (site navigation)."""
    pages = [(page, url)]
    errors: list[str] = []
    if listing.page_template:
        for n in range(1, listing.pages):
            nxt = listing.page_template.format(url=listing.url, offset=n * listing.page_step, n=n + 1)
            try:
                pages.append(f.get(nxt))
            except (httpx.HTTPError, DiscoveryError) as e:
                errors.append(_err(e))
                break
    body: list[str] = []

    def keep(link: str) -> bool:
        return not listing.url_pattern or bool(re.search(listing.url_pattern, link))

    def link_row(title: str, link: str) -> str:
        name = html_lib.escape(link.rsplit("/", 1)[-1])
        return f'<tr><td>{html_lib.escape(title)}</td><td><a href="{html_lib.escape(link)}">{name}</a></td></tr>'

    if listing.follow:
        details: list[tuple[str, str]] = []
        for pg, pu in pages:
            for m in _A.finditer(pg):
                href = html_lib.unescape(m.group(1) or m.group(2) or m.group(3) or "")
                full = urljoin(pu, href)
                if re.search(listing.follow, href) and full not in [d[1] for d in details]:
                    details.append((_text(m.group(4)), full))
        for title, durl in details[: listing.max_follow]:
            try:
                dpage, dfinal = f.get(durl)
            except (httpx.HTTPError, DiscoveryError) as e:
                errors.append(f"{durl}: {_err(e)}")
                continue
            body += [link_row(title, pdf) for pdf in pdf_links(dpage, dfinal) if keep(pdf)]
    else:
        from .library import _HREF, _ROW

        for pg, pu in pages:
            # a PDF link inside a table row keeps its row, so the proposer finds the row's title
            in_rows: set[str] = set()
            for row in _ROW.finditer(pg):
                links = [
                    urljoin(pu, html_lib.unescape(m.group(1) or m.group(2) or m.group(3) or ""))
                    for m in _HREF.finditer(row.group(1))
                ]
                pdfs = [x for x in links if re.search(r"\.pdf(\?|#|$)", x, re.I)]
                if not pdfs or not any(keep(x) for x in pdfs):
                    continue
                in_rows.update(pdfs)
                body.append("<tr>" + _absolute(row.group(1), pu) + "</tr>")
            for m in [] if listing.rows_only else _HREF.finditer(pg):
                full = urljoin(pu, html_lib.unescape(m.group(1) or m.group(2) or m.group(3) or ""))
                if re.search(r"\.pdf(\?|#|$)", full, re.I) and full not in in_rows and keep(full):
                    in_rows.add(full)
                    body.append(link_row(_text(m.group(4)), full))
    return [
        {
            "listing": listing.name,
            "fiscal_year": "",
            "url": url,
            "html": "<table>" + "".join(body) + "</table>",
            "error": "; ".join(errors) or None,
        }
    ]


_HREF_ATTR = re.compile(r"""href\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>"']+))""", re.I)


def _absolute(fragment: str, base: str) -> str:
    """The fragment with every href made absolute (rows are gathered from several pages)."""

    def repl(m: re.Match) -> str:
        return (
            'href="' + html_lib.escape(urljoin(base, html_lib.unescape(m.group(1) or m.group(2) or m.group(3)))) + '"'
        )

    return _HREF_ATTR.sub(repl, fragment)


def _text(fragment: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _err(e: Exception) -> str:
    return str(e) if isinstance(e, DiscoveryError) else f"request failed: {type(e).__name__}"


def run(
    profile: Profile,
    fiscal_years: list[str],
    *,
    licensees: dict[str, list[str]],
    fetcher: Fetcher | None = None,
    propose: Callable[..., list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Every listing of the profile for the years asked: proposals (deduplicated by URL and
    licensee) and a line per page fetched, with its count or its error."""
    from .library import propose_from_html

    propose = propose or propose_from_html
    f = fetcher or Fetcher()
    licensees = {code: [*names, *profile.licensee_aliases.get(code, [])] for code, names in licensees.items()}
    pages: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    try:
        for listing in profile.listings:
            for pg in fetch_listing(f, listing, fiscal_years):
                found = 0
                if pg["html"] is not None:
                    label = f"{pg['listing']} {pg['fiscal_year']}".strip()
                    for p in propose(
                        pg["html"][:5_000_000],
                        pg["url"],
                        licensees=licensees,
                        groups=profile.licensee_groups,
                        listing=label,
                        default_licensee=listing.licensee if listing.licensee in licensees else None,
                        since=min(fiscal_years, key=lambda y: int(y[2:6])) if fiscal_years else None,
                    ):
                        key = (p["url"], p["utility_code"])
                        if key in seen:
                            continue
                        seen.add(key)
                        proposals.append(p)
                        found += 1
                pages.append(
                    {
                        "listing": pg["listing"],
                        "fiscal_year": pg["fiscal_year"],
                        "url": pg["url"],
                        "documents": found,
                        "error": pg["error"],
                    }
                )
    finally:
        f.close()
    return {
        "profile": {
            "id": profile.id,
            "version": profile.version,
            "status": profile.status,
            "commission": profile.commission,
        },
        "pages": pages,
        "proposals": proposals,
        "requests": f.requests,
    }
