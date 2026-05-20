"""
SPA Email Extractor — Playwright-based.
Handles JavaScript-rendered sites, phone trees, and dynamic content.
"""

import re
import json
import asyncio
import os
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright, Page
from scraper.utils import (
    EMAIL_PATTERN,
    OBFUSCATED_EMAIL_PATTERN,
    REQUEST_HEADERS,
    is_priority_link,
    is_junk_email,
)

# Expanded route list — covers many real-world contact page paths
COMMON_EMAIL_ROUTES = [
    # Contact variants
    "/contact", "/contact-us", "/contacts", "/contact-info",
    "/get-in-touch", "/reach-us", "/reach-out",
    "/contactus", "/contact_us",
    # About / team
    "/about", "/about-us", "/aboutus", "/about_us",
    "/our-story", "/our-team", "/team", "/staff",
    "/who-we-are", "/meet-the-team", "/leadership",
    "/company", "/company-info",
    # Support / help
    "/support", "/help", "/help-center", "/faq",
    # Info / legal
    "/info", "/information", "/impressum",
    "/privacy", "/privacy-policy",
    "/legal", "/legal-notice",
    # Location / office
    "/location", "/locations", "/offices", "/office",
    "/find-us", "/directions", "/visit-us",
    # Partners / join
    "/partners", "/partnership",
    "/join-us", "/work-with-us", "/careers",
    # Feedback / social
    "/feedback", "/social",
    # Common CMS paths
    "/pages/contact", "/pages/about",
    "/en/contact", "/en/about",
]

# Ad/tracker domains to block (reduces load time, not needed for email extraction)
_BLOCKED_DOMAINS = [
    "analytics", "doubleclick", "tracker", "facebook.com",
    "adservice", "googlesyndication", "googletagmanager",
    "hotjar", "mixpanel", "segment.io", "amplitude",
]


async def extract_emails_from_page(page: Page, debug=False) -> set[str]:
    emails: set[str] = set()

    try:
        content = await page.content()
    except Exception:
        content = ""

    try:
        text = await page.inner_text("body")
    except Exception:
        text = ""

    emails.update(re.findall(EMAIL_PATTERN, content))
    emails.update(re.findall(EMAIL_PATTERN, text))

    # Obfuscated pattern (e.g. "user [at] domain [dot] com")
    for parts in re.findall(OBFUSCATED_EMAIL_PATTERN, text):
        emails.add(f"{parts[0]}@{parts[1]}.{parts[2]}")

    # mailto: links
    try:
        for element in await page.query_selector_all("a[href^='mailto:']"):
            href = await element.get_attribute("href")
            if href:
                addr = href.replace("mailto:", "").split("?")[0].strip().lower()
                if addr:
                    emails.add(addr)
    except Exception:
        pass

    # JSON-LD structured data
    try:
        ld_scripts = await page.query_selector_all("script[type='application/ld+json']")
        for script_el in ld_scripts:
            raw = await script_el.inner_text()
            try:
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item.get("email"), str):
                        emails.add(item["email"].lower())
                    for cp in item.get("contactPoint", []):
                        if isinstance(cp.get("email"), str):
                            emails.add(cp["email"].lower())
            except Exception:
                pass
    except Exception:
        pass

    # data-email / data-mail attributes
    try:
        for attr in ("data-email", "data-mail", "data-contact"):
            els = await page.query_selector_all(f"[{attr}]")
            for el in els:
                val = await el.get_attribute(attr)
                if val:
                    emails.update(re.findall(EMAIL_PATTERN, val))
    except Exception:
        pass

    result = {e.lower() for e in emails if e and not is_junk_email(e)}

    if debug:
        print(f"[DEBUG] Extracted {len(result)} email(s) from page.")

    return result


async def extract_navigation_links(page: Page, base_url: str, debug=False) -> set[str]:
    links: set[str] = set()
    current_url = page.url or base_url  # use actual current URL as base

    async def _from(selector: str, limit=None):
        try:
            elements = await page.query_selector_all(selector)
            for a in (elements[:limit] if limit else elements):
                href = await a.get_attribute("href")
                if href and not href.startswith(("javascript:", "#", "tel:", "mailto:")):
                    links.add(urljoin(current_url, href))
        except Exception:
            pass

    await _from("nav a[href]")
    await _from("header a[href]")
    await _from("footer a[href]")      # footer often has contact/about
    await _from("aside a[href]")
    await _from("a[href]", limit=150)  # fallback catch-all

    if debug:
        print(f"[DEBUG] Found {len(links)} navigation links.")
    return links


async def visit_url(page: Page, url: str, debug=False) -> set[str]:
    """Navigate to url and extract emails. Tolerates networkidle timeout."""
    emails: set[str] = set()
    try:
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        # Give JS up to 4 seconds to hydrate; don't block forever on analytics
        try:
            await asyncio.wait_for(
                asyncio.ensure_future(page.wait_for_load_state("networkidle")),
                timeout=4,
            )
        except (asyncio.TimeoutError, Exception):
            pass  # proceed with whatever is rendered so far
        emails = await extract_emails_from_page(page, debug=debug)
    except Exception as e:
        if debug:
            print(f"[ERROR] Visiting {url}: {e}")
    return emails


async def spa_extract_emails_recursive(
    start_url: str,
    max_depth: int = 2,
    tmp_file: str = "tmp_file.txt",
    debug: bool = False,
) -> list[str]:

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox",
                "--ignore-certificate-errors",
                "--allow-insecure-localhost",
            ],
        )

        context = await browser.new_context(
            user_agent=REQUEST_HEADERS["User-Agent"],
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept-Language": REQUEST_HEADERS["Accept-Language"],
            },
        )
        page = await context.new_page()

        async def block_resources(route):
            req = route.request
            if req.resource_type in {"image", "media", "font"}:
                await route.abort()
            elif any(kw in req.url for kw in _BLOCKED_DOMAINS):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", block_resources)
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(20000)

        visited_urls: set[str] = set()
        all_emails: set[str] = set()
        base_domain = urlparse(start_url).netloc

        def _flush():
            with open(tmp_file, "w", encoding="utf-8") as f:
                for e in all_emails:
                    f.write(f"{e}\n")
                f.flush()
                os.fsync(f.fileno())

        # ── Step 1: homepage ─────────────────────────────────────────────────
        main_emails = await visit_url(page, start_url, debug)
        all_emails.update(main_emails)
        visited_urls.add(start_url)
        _flush()

        # ── Step 2: build initial link set ───────────────────────────────────
        nav_links = await extract_navigation_links(page, start_url, debug)
        nav_links = {l for l in nav_links if urlparse(l).netloc == base_domain}

        # Add all heuristic routes; filter to same domain
        heuristic_links = {
            urljoin(start_url, route) for route in COMMON_EMAIL_ROUTES
        }

        to_visit_set = (nav_links | heuristic_links) - visited_urls

        # Sort: priority pages first
        relative_links = sorted(
            [urlparse(l).path for l in to_visit_set],
            key=lambda path: 0 if is_priority_link(path) else 1,
        )

        # ── Step 3: recursive exploration ────────────────────────────────────
        for depth in range(max_depth):
            if debug:
                print(f"\n[INFO] Depth {depth + 1}/{max_depth}")

            next_relative_links: list[str] = []

            for rel_link in relative_links:
                full_url = urljoin(start_url, rel_link)
                if full_url in visited_urls:
                    continue
                visited_urls.add(full_url)

                if debug:
                    print(f"[INFO] Visiting: {full_url}")

                emails = await visit_url(page, full_url, debug=debug)
                all_emails.update(emails)
                _flush()

                # Gather links from this page for the next depth
                new_links = await extract_navigation_links(page, full_url, debug=debug)
                new_links = {l for l in new_links if urlparse(l).netloc == base_domain}
                new_rels = [
                    urlparse(l).path for l in new_links
                    if urljoin(start_url, urlparse(l).path) not in visited_urls
                ]
                next_relative_links.extend(
                    sorted(new_rels, key=lambda l: 0 if is_priority_link(l) else 1)
                )

            if not next_relative_links:
                if debug:
                    print("[INFO] No more links to visit.")
                break

            relative_links = next_relative_links

        await browser.close()

    return sorted(all_emails)
