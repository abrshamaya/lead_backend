import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# ── Priority contact-page keywords ───────────────────────────────────────────
PRIORITY_KEYWORDS = [
    "contact", "about", "team", "support", "staff", "help",
    "connect", "info", "impressum", "legal", "privacy", "reach",
    "location", "office", "directory", "company", "who-we-are",
]

# ── File extensions that are never HTML ──────────────────────────────────────
BAD_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".svg", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".zip", ".rar", ".7z", ".mp3",
    ".mp4", ".avi", ".mov", ".wmv", ".txt", ".csv",
    ".woff", ".woff2", ".ttf", ".eot", ".ico",
)

# ── Email patterns ────────────────────────────────────────────────────────────
EMAIL_PATTERN = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
OBFUSCATED_EMAIL_PATTERN = (
    r"([a-zA-Z0-9_.+-]+)\s*\[at\]\s*([a-zA-Z0-9-]+)\s*\[dot\]\s*([a-zA-Z.]+)"
)

# ── Junk email prefixes (not useful business contacts) ───────────────────────
JUNK_EMAIL_PREFIXES = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce", "bounces",
    "automated", "auto-reply", "auto",
    "notifications", "notification",
    "unsubscribe", "subscribe",
    "wordpress", "drupal", "wix", "shopify",
    "example", "test", "demo",
}

# ── Realistic browser headers ─────────────────────────────────────────────────
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def is_junk_email(email: str) -> bool:
    """Return True for emails that are definitely not useful business contacts."""
    local = email.split("@")[0].lower().strip()
    return local in JUNK_EMAIL_PREFIXES or any(
        local.startswith(p + "+") or local.startswith(p + ".")
        for p in JUNK_EMAIL_PREFIXES
    )


def is_spa_site(url: str, timeout: int = 15, debug=False) -> bool:
    """
    Heuristically decide whether a URL is a client-side (SPA) app.
    Improved over the original: framework keyword check now looks at
    script src attributes instead of visible body text, which caused
    false positives on any page that *mentioned* React/Vue in content.
    """
    try:
        res = requests.get(url, timeout=timeout, headers=REQUEST_HEADERS)
        if not res.ok:
            return True  # fallback: try SPA scraper on error
        soup = BeautifulSoup(res.text, "html.parser")

        # 1. Almost empty body → definitely SPA
        body = soup.body
        body_text = body.get_text(strip=True) if body else ""
        if not body or len(body_text) < 100:
            return True

        # 2. Common SPA root elements with little/no server-rendered content
        for root_id in ("root", "__next", "app", "__nuxt", "gatsby-focus-wrapper"):
            el = soup.find(id=root_id)
            if el and len(el.get_text(strip=True)) < 200:
                return True

        # 3. Data attributes injected by SPA frameworks
        if (
            soup.find(attrs={"data-reactroot": True})
            or soup.find(attrs={"ng-version": True})
            or soup.find(attrs={"data-server-rendered": True})
        ):
            return True

        # 4. Framework hints in script *src* attributes (not body text)
        for script in soup.find_all("script", src=True):
            src = script["src"].lower()
            if any(fw in src for fw in ["react", "vue", "angular", "next", "nuxt", "svelte"]):
                return True

        # 5. Lots of scripts, almost no readable content
        scripts = soup.find_all("script")
        if len(scripts) > 20 and len(body_text) < 300:
            return True

        return False

    except Exception as e:
        if debug:
            print(f"[WARN] SPA detection error: {e}")
        return False  # default to static scraper on error


def is_same_domain(base_url: str, target_url: str) -> bool:
    return urlparse(base_url).netloc == urlparse(target_url).netloc


def is_valid_html_link(href: str) -> bool:
    if not href:
        return False
    href = href.lower()
    if href.startswith(("mailto:", "tel:", "#", "javascript:")):
        return False
    if any(href.endswith(ext) for ext in BAD_EXTENSIONS):
        return False
    return True


def is_priority_link(href: str) -> bool:
    return any(keyword in href.lower() for keyword in PRIORITY_KEYWORDS)
