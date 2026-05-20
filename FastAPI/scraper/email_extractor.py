import re
import os
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup, Comment
from urllib.parse import urljoin, urlparse, urldefrag
from scraper.utils import (
    EMAIL_PATTERN,
    BAD_EXTENSIONS,
    OBFUSCATED_EMAIL_PATTERN,
    PRIORITY_KEYWORDS,
    REQUEST_HEADERS,
    is_same_domain,
    is_valid_html_link,
    is_priority_link,
    is_junk_email,
)


def make_session() -> requests.Session:
    """Session with retry logic and realistic browser headers."""
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(REQUEST_HEADERS)
    return session


def extract_emails_from_text(text: str) -> set[str]:
    emails = set(re.findall(EMAIL_PATTERN, text))
    for parts in re.findall(OBFUSCATED_EMAIL_PATTERN, text):
        emails.add(f"{parts[0]}@{parts[1]}.{parts[2]}")
    return {e.lower() for e in emails if not is_junk_email(e)}


def extract_emails_from_jsonld(soup: BeautifulSoup) -> set[str]:
    """Pull emails out of JSON-LD structured data (schema.org markup)."""
    emails = set()
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = script.string or ""
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            for item in items:
                # Direct email field
                if isinstance(item.get("email"), str):
                    emails.add(item["email"].lower())
                # contactPoint array
                for cp in item.get("contactPoint", []):
                    if isinstance(cp.get("email"), str):
                        emails.add(cp["email"].lower())
                # sameAs / url fields (sometimes contain mailto:)
                for val in item.get("sameAs", []):
                    if isinstance(val, str) and val.startswith("mailto:"):
                        emails.add(val[7:].lower())
        except Exception:
            pass
    return {e for e in emails if not is_junk_email(e)}


def discover_sitemap_contact_urls(base_url: str, session: requests.Session) -> set[str]:
    """
    Fetch /sitemap.xml (and /sitemap_index.xml) and return any URLs whose
    path contains a contact/about keyword.  These are high-value pages.
    """
    contact_urls = set()
    candidates = [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"),
        urljoin(base_url, "/sitemap"),
    ]
    for sm_url in candidates:
        try:
            r = session.get(sm_url, timeout=8)
            if not r.ok or "xml" not in r.headers.get("content-type", ""):
                continue
            sm_soup = BeautifulSoup(r.text, "xml")
            locs = [tag.get_text() for tag in sm_soup.find_all("loc")]
            for loc in locs:
                if is_same_domain(base_url, loc) and is_priority_link(loc):
                    contact_urls.add(loc)
        except Exception:
            pass
    return contact_urls


def extract_links(soup: BeautifulSoup, base_url: str) -> set[str]:
    """
    Collect all same-domain links from the page, always including links
    from nav, header, footer, and the full body.  Results are returned
    as a set; callers should sort by is_priority_link().
    """
    links = set()

    def _add_from(selector_tags):
        for section in soup.find_all(selector_tags):
            for a in section.find_all("a", href=True):
                href = a["href"]
                if is_valid_html_link(href):
                    href, _ = urldefrag(href)
                    full_url = urljoin(base_url, href)
                    if is_same_domain(base_url, full_url):
                        links.add(full_url)

    # Structural sections first (fast, usually correct)
    _add_from(["nav", "header", "footer", "aside"])

    # Always fall back to full body to catch anything the structure missed
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if is_valid_html_link(href):
            href, _ = urldefrag(href)
            full_url = urljoin(base_url, href)
            if is_same_domain(base_url, full_url):
                links.add(full_url)

    return links


def scrape_page(url: str, session: requests.Session, debug=False) -> tuple[set[str], set[str]]:
    emails: set[str] = set()
    links: set[str] = set()

    try:
        response = session.get(url, timeout=20, allow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Visible text
        emails |= extract_emails_from_text(soup.get_text())

        # mailto: links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                addr = href[7:].split("?")[0].strip().lower()
                if addr and not is_junk_email(addr):
                    emails.add(addr)

        # HTML attributes
        for tag in soup.find_all(True):
            for attr in ("title", "alt", "data-email", "data-mail", "data-contact", "content"):
                val = tag.attrs.get(attr, "")
                if val:
                    emails |= extract_emails_from_text(val)

        # <meta> tag content (og:email, twitter:email, etc.)
        for meta in soup.find_all("meta"):
            content = meta.get("content", "")
            if content:
                emails |= extract_emails_from_text(content)

        # JSON-LD structured data (schema.org)
        emails |= extract_emails_from_jsonld(soup)

        # Inline <script> blocks
        for script in soup.find_all("script"):
            if script.string:
                emails |= extract_emails_from_text(script.string)

        # HTML comments
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            emails |= extract_emails_from_text(comment)

        # Links for crawling
        links = extract_links(soup, url)

    except requests.RequestException as e:
        if debug:
            print(f"[ERROR] Failed to access {url}: {e}")

    return emails, links


def extract_emails_recursive(
    start_url: str,
    max_depth: int = 2,
    tmp_file: str = "tmp_file.txt",
    debug: bool = False,
) -> list[str]:
    session = make_session()
    visited: set[str] = set()
    all_emails: set[str] = set()

    # Seed with homepage + any contact pages found via sitemap
    sitemap_contacts = discover_sitemap_contact_urls(start_url, session)
    to_visit: set[str] = {start_url} | sitemap_contacts

    if debug and sitemap_contacts:
        print(f"[INFO] Sitemap gave {len(sitemap_contacts)} contact pages")

    for depth in range(max_depth):
        if debug:
            print(f"\n[INFO] Depth {depth + 1}/{max_depth} — {len(to_visit)} URLs")

        next_to_visit: set[str] = set()

        # Sort so priority pages (contact, about, …) are visited first
        ordered = sorted(to_visit, key=lambda l: 0 if is_priority_link(l) else 1)

        for url in ordered:
            if url in visited:
                continue
            visited.add(url)

            if debug:
                print(f"[INFO] Crawling: {url}")

            emails, links = scrape_page(url, session, debug=debug)
            all_emails |= emails

            # Write partial results so the parent process can read them on timeout
            with open(tmp_file, "w", encoding="utf-8") as f:
                for e in all_emails:
                    f.write(f"{e}\n")
                f.flush()
                os.fsync(f.fileno())

            priority_links = sorted(links, key=lambda l: 0 if is_priority_link(l) else 1)
            next_to_visit |= {l for l in priority_links if l not in visited}

        to_visit = next_to_visit
        if not to_visit:
            break

    return sorted(all_emails)
