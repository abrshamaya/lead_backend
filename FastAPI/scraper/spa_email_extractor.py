# Optimized SPA Email Extractor — skips images, videos, fonts, and ads for speed.
# Maintains full compatibility with the existing scraper pipeline.

import re
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright, Page
from scraper.utils import EMAIL_PATTERN, OBFUSCATED_EMAIL_PATTERN, is_priority_link


async def extract_emails_from_page(page: Page, debug=False) -> set[str]:
    emails = set()

    try:
        content = await page.content()
        text = await page.inner_text("body")
    except Exception:
        content, text = "", ""

    # Normal + obfuscated emails
    emails.update(re.findall(EMAIL_PATTERN, content))
    emails.update(re.findall(EMAIL_PATTERN, text))

    # Mailto links
    try:
        for element in await page.query_selector_all("a[href^='mailto:']"):
            href = await element.get_attribute("href")
            if href:
                emails.add(href.replace("mailto:", "").strip())
    except Exception:
        pass

    # Obfuscated forms like "user [at] domain [dot] com"
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
                if href:
                    links.add(urljoin(base_url, href))
        except Exception:
            pass

    await extract_from("nav a[href]")
    if not links:
        await extract_from("header a[href]")
    if not links:
        await extract_from("a[href]", limit=50)

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
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            await page.wait_for_timeout(1500)

        emails = await extract_emails_from_page(page, debug=debug)

        # Return to main page fast
        try:
            await page.goto(base_url, timeout=20000, wait_until="domcontentloaded")
        except Exception:
            await page.wait_for_timeout(2000)
    except Exception as e:
        if debug:
            print(f"[ERROR] Clicking link {relative_url}: {e}")

    return emails


async def spa_extract_emails_recursive(start_url: str, max_depth: int = 2, debug=False) -> list[str]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
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

        # Timeouts
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(25000)

        visited_urls = set()
        all_emails = set()
        base_domain = urlparse(start_url).netloc

        # Load the first page
        try:
            await page.goto(start_url, timeout=30000, wait_until="domcontentloaded")
        except Exception:
            if debug:
                print("[WARN] Initial load failed, retrying slower.")
            await page.goto(start_url, timeout=60000)

        emails = await extract_emails_from_page(page, debug=debug)
        all_emails.update(email.lower() for email in emails)

        # Collect navigation links
        to_visit = await extract_navigation_links(page, start_url, debug=debug)
        to_visit = {link for link in to_visit if urlparse(link).netloc == base_domain}
        priority_links = sorted(to_visit, key=lambda l: 0 if is_priority_link(l) else 1)
        relative_links = [urlparse(link).path for link in priority_links]

        # Recursive scraping
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
                next_relative_links.extend(
                    sorted(new_rel_links, key=lambda l: 0 if is_priority_link(l) else 1)
                )

            if not next_relative_links:
                if debug:
                    print("[INFO] No more links to visit, stopping early.")
                break

            relative_links = next_relative_links

        await browser.close()
        return sorted(all_emails)
