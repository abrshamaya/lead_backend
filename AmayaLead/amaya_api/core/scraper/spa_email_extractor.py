
# A more powerful email extractor to also handle SPA applications.
# For simpler websites, the older email extractor can be used.

import re
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Page
from .utils import (
    EMAIL_PATTERN,
    OBFUSCATED_EMAIL_PATTERN,
    is_priority_link
)


async def extract_emails_from_page(page: Page, debug=False) -> set[str]:
    emails = set()

    content = await page.content()
    text = await page.inner_text("body")

    emails.update(re.findall(EMAIL_PATTERN, content))
    emails.update(re.findall(EMAIL_PATTERN, text))

    for element in await page.query_selector_all("a[href^='mailto:']"):
        href = await element.get_attribute("href")
        if href:
            emails.add(href.replace("mailto:", "").strip())

    for parts in re.findall(OBFUSCATED_EMAIL_PATTERN, text):
        emails.add(f"{parts[0]}@{parts[1]}.{parts[2]}")

    if debug:
        print(f"[DEBUG] Extracted {len(emails)} emails from page.")

    return emails

async def extract_navigation_links(page: Page, base_url: str, debug=False) -> set[str]:
    links = set()

    navs = await page.query_selector_all("nav")
    for nav in navs:
        anchors = await nav.query_selector_all("a[href]")
        for a in anchors:
            href = await a.get_attribute("href")
            if href:
                full_url = urljoin(base_url, href)
                links.add(full_url)

    if not links:
        headers = await page.query_selector_all("header")
        for header in headers:
            anchors = await header.query_selector_all("a[href]")
            for a in anchors:
                href = await a.get_attribute("href")
                if href:
                    full_url = urljoin(base_url, href)
                    links.add(full_url)

    if not links:
        anchors = await page.query_selector_all("a[href]")
        for a in anchors[:50]:
            href = await a.get_attribute("href")
            if href:
                full_url = urljoin(base_url, href)
                links.add(full_url)

    if debug:
        print(f"[DEBUG] Extracted {len(links)} navigation links.")

    return links

async def click_link_and_extract_emails(page: Page, relative_url: str, base_url: str, debug=False) -> set[str]:
    emails = set()
    try:
        anchor = await page.query_selector(
            f"a[href='{relative_url}'], a[href='{urljoin(base_url, relative_url)}']"
        )
        if not anchor:
            if debug:
                print(f"[WARN] No clickable link found for {relative_url}")
            return emails

        await anchor.click()

        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            await page.wait_for_timeout(2000)

        emails = await extract_emails_from_page(page, debug=debug)

        await page.goto(base_url,timeout=40000)
        try:
            await page.wait_for_load_state("networkidle")
        except:
            await page.wait_for_timeout(2000)
    except Exception as e:
        if debug:
            print(f"[ERROR] Clicking link {relative_url}: {e}")

    return emails

async def spa_extract_emails_recursive(start_url: str, max_depth: int = 2, debug=False) -> list[str]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        visited_urls = set()
        all_emails = set()
        base_domain = urlparse(start_url).netloc

        await page.goto(start_url,timeout=40000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except:
            await page.wait_for_timeout(2000)

        emails = await extract_emails_from_page(page, debug=debug)
        all_emails.update(email.lower() for email in emails)

        to_visit = await extract_navigation_links(page, start_url, debug=debug)
        to_visit = {link for link in to_visit if urlparse(link).netloc == base_domain}
        priority_links = sorted(to_visit, key=lambda l: 0 if is_priority_link(l) else 1)
        relative_links = [urlparse(link).path for link in priority_links]

        for depth in range(max_depth):
            if debug:
                print(f"\n[INFO] Depth {depth + 1}/{max_depth}")

            next_relative_links = []
            for rel_link in relative_links:
                if rel_link in visited_urls:
                    continue
                visited_urls.add(rel_link)
                if debug:
                    print(f"[INFO] Clicking and scraping: {rel_link}")

                emails = await click_link_and_extract_emails(page, rel_link, start_url, debug=debug)
                all_emails.update(email.lower() for email in emails)

                links = await extract_navigation_links(page, start_url, debug=debug)
                links = {link for link in links if urlparse(link).netloc == base_domain}

                new_rel_links = [
                    urlparse(link).path for link in links if urlparse(link).path not in visited_urls
                ]

                new_rel_links_sorted = sorted(new_rel_links, key=lambda l: 0 if is_priority_link(l) else 1)
                next_relative_links.extend(new_rel_links_sorted)

            if not next_relative_links:
                if debug:
                    print("[INFO] No more links to visit, stopping early.")
                break

            relative_links = next_relative_links

        await browser.close()
        return sorted(all_emails)

