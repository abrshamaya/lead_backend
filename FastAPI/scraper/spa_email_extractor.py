
# Optimized SPA Email Extractor — minimal clicking, route heuristics, skips images/videos/fonts/ads.
# Maintains full compatibility with the existing scraper pipeline.

import re
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright, Page
from scraper.utils import EMAIL_PATTERN, OBFUSCATED_EMAIL_PATTERN, is_priority_link
import os


COMMON_EMAIL_ROUTES = [
    "/contact", "/contact-us", "/get-in-touch", "/reach-us",
    "/about", "/about-us", "/our-story", "/company", "/team",
    "/support",
    "/info", "/information", "/legal", "/partners", "/partnership", "/join-us",
    "/feedback",
    "/social"
]

async def extract_emails_from_page(page: Page, debug=False) -> set[str]:
    emails = set()

    try:
        content = await page.content()
        text = await page.inner_text("body")
    except Exception:
        content, text = "", ""

    emails.update(re.findall(EMAIL_PATTERN, content))
    emails.update(re.findall(EMAIL_PATTERN, text))

    try:
        for element in await page.query_selector_all("a[href^='mailto:']"):
            href = await element.get_attribute("href")
            if href:
                emails.add(href.replace("mailto:", "").strip())
    except Exception:
        pass

    for parts in re.findall(OBFUSCATED_EMAIL_PATTERN, text):
        emails.add(f"{parts[0]}@{parts[1]}.{parts[2]}")

    if debug:
        print(f"[DEBUG] Extracted {len(emails)} emails from page.")

    return emails


async def extract_navigation_links(page: Page, base_url: str, debug=False) -> set[str]:
    links = set()

    async def extract_from(selector: str, limit=None):
        try:
            elements = await page.query_selector_all(selector)
            for a in elements[:limit] if limit else elements:
                href = await a.get_attribute("href")
                if href and not href.startswith("javascript:") and not href.startswith("#"):
                    links.add(urljoin(base_url, href))
        except Exception:
            pass

    # Prioritize structural containers
    await extract_from("nav a[href]")      # main nav
    await extract_from("header a[href]")   # headers
    await extract_from("footer a[href]")   # footers often have contact/info links
    await extract_from("aside a[href]")    # sidebars
    await extract_from("section a[href]")  # generic sections
    await extract_from("a[href]", limit=100)  # fallback catch-all

    if debug:
        print(f"[DEBUG] Extracted {len(links)} navigation links.")

    return links



async def visit_url_and_extract_emails(page: Page, url: str, debug=False) -> set[str]:
    emails = set()
    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        emails = await extract_emails_from_page(page, debug=debug)
    except Exception as e:
        if debug:
            print(f"[ERROR] Visiting {url}: {e}")
    return emails


async def spa_extract_emails_recursive(start_url: str, max_depth: int = 2, tmp_file='tmp_file.txt', debug=False) -> list[str]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--ignore-certificate-errors",  # ignore SSL errors
                "--allow-insecure-localhost",   # allow self-signed certs on localhost
               ],
        )
        page = await browser.new_page()

        async def block_resources(route):
            req = route.request
            if req.resource_type in {"image", "media", "font"}:
                await route.abort()
            elif any(keyword in req.url for keyword in [
                "analytics", "doubleclick", "tracker", "facebook", "adservice",
            ]):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", block_resources)
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(25000)

        visited_urls = set()
        all_emails = set()
        base_domain = urlparse(start_url).netloc

        # Start with the main page
        main_emails = await visit_url_and_extract_emails(page, start_url, debug)
        all_emails.update(email.lower() for email in main_emails)

        with open(tmp_file, "w", encoding='utf-8') as f:
            for email in all_emails:
                f.write(f"{email}\n")
                f.flush()
                os.fsync(f.fileno())

        # Collect initial links
        to_visit = await extract_navigation_links(page, start_url, debug)
        to_visit = {link for link in to_visit if urlparse(link).netloc == base_domain}

        # Add heuristic routes (contact/about/etc.)
        to_visit.update(urljoin(start_url, route) for route in COMMON_EMAIL_ROUTES)

        # Sort by priority
        priority_links = sorted(to_visit, key=lambda l: 0 if is_priority_link(l) else 1)
        relative_links = [urlparse(link).path for link in priority_links]

        # Recursive exploration
        for depth in range(max_depth):
            if debug:
                print(f"\n[INFO] Depth {depth + 1}/{max_depth}")

            next_relative_links = []
            for rel_link in relative_links:
                full_url = urljoin(start_url, rel_link)
                if full_url in visited_urls:
                    continue
                visited_urls.add(full_url)

                if debug:
                    print(f"[INFO] Visiting: {full_url}")

                emails = await visit_url_and_extract_emails(page, full_url, debug=debug)
                all_emails.update(email.lower() for email in emails)
                with open(tmp_file, "w", encoding='utf-8') as f:
                    for email in all_emails:
                        f.write(f"{email}\n")
                        f.flush()
                        os.fsync(f.fileno())
                # Collect new links without clicking
                new_links = await extract_navigation_links(page, start_url, debug=debug)
                new_links = {link for link in new_links if urlparse(link).netloc == base_domain}

                new_rel_links = [urlparse(link).path for link in new_links if urljoin(start_url, urlparse(link).path) not in visited_urls]
                next_relative_links.extend(sorted(new_rel_links, key=lambda l: 0 if is_priority_link(l) else 1))

            if not next_relative_links:
                if debug:
                    print("[INFO] No more links to visit, stopping early.")
                break

            relative_links = next_relative_links

        await browser.close()
        return sorted(all_emails)
