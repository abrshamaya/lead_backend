
import re
import os
import requests
from bs4 import BeautifulSoup, Comment
from urllib.parse import urljoin, urlparse, urldefrag
from scraper.utils import (
    EMAIL_PATTERN,
    BAD_EXTENSIONS,
    OBFUSCATED_EMAIL_PATTERN,
    PRIORITY_KEYWORDS,
    is_same_domain,
    is_valid_html_link,
    is_priority_link
)

def extract_emails_from_text(text: str) -> set[str]:
    emails = set(re.findall(EMAIL_PATTERN, text))
    for parts in re.findall(OBFUSCATED_EMAIL_PATTERN, text):
        emails.add(f"{parts[0]}@{parts[1]}.{parts[2]}")
    return emails

def extract_links(soup: BeautifulSoup, base_url: str) -> set[str]:
    links = set()

    # Prioritize <nav> or <header> links
    for section in soup.find_all(['nav', 'header']):
        for a in section.find_all('a', href=True):
            href = a['href']
            if is_valid_html_link(href):
                href, _ = urldefrag(href)
                full_url = urljoin(base_url, href)
                if is_same_domain(base_url, full_url):
                    links.add(full_url)

    # Fallback: all a[href] tags
    if not links:
        for a in soup.find_all('a', href=True):
            href = a['href']
            if is_valid_html_link(href):
                href, _ = urldefrag(href)
                full_url = urljoin(base_url, href)
                if is_same_domain(base_url, full_url):
                    links.add(full_url)

    return links

def scrape_page(url: str, debug=False) -> tuple[set[str], set[str]]:
    emails = set()
    links = set()

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract from visible text
        emails |= extract_emails_from_text(soup.get_text())

        # Extract from mailto: links
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('mailto:'):
                email = href[7:].split('?')[0]  # ignore query params
                emails.add(email.lower())

        # Extract from useful attributes
        ATTRIBUTES_TO_SCAN = ['title', 'alt', 'data-email', 'data-contact', 'content']
        for tag in soup.find_all(True):
            for attr in ATTRIBUTES_TO_SCAN:
                if attr in tag.attrs:
                    attr_text = tag[attr]
                    emails |= extract_emails_from_text(attr_text)

        # Extract from script tags
        for script in soup.find_all('script'):
            if script.string:
                emails |= extract_emails_from_text(script.string)

        # Extract from HTML comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            emails |= extract_emails_from_text(comment)

        # Extract links
        links = extract_links(soup, url)

    except requests.RequestException as e:
        if debug:
            print(f"[ERROR] Failed to access {url}: {e}")

    return emails, links

def extract_emails_recursive(start_url: str, max_depth: int = 2, tmp_file='tmp_file.txt',debug=False) -> list[str]:
    visited = set()
    to_visit = {start_url}
    all_emails = set()

    for depth in range(max_depth):
        if debug:
            print(f"\n[INFO] Depth {depth+1}/{max_depth}")
        next_to_visit = set()

        for url in to_visit:
            if url in visited:
                continue
            visited.add(url)

            if debug:
                print(f"[INFO] Crawling: {url}")
            emails, links = scrape_page(url, debug=debug)  
            all_emails |= {email.lower() for email in emails}
            with open(tmp_file, 'w') as f:
                for email in all_emails:
                    f.write(f"{email}\n")
                    f.flush()
                    os.fsync(f.fileno())

            priority_links = sorted(links, key=lambda l: 0 if is_priority_link(l) else 1)
            next_to_visit |= {l for l in priority_links if l not in visited}

        to_visit = next_to_visit
        if not to_visit:
            break

    return sorted(all_emails)

