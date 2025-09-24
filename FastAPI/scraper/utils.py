import requests
from urllib.parse import  urlparse
from bs4 import BeautifulSoup

# Heuristic priority keywords
PRIORITY_KEYWORDS = [
    "contact", "about", "team", "support", "staff", "help",
    "connect", "info", "impressum", "legal", "privacy", "terms"
]

# Non-HTML file types to skip
BAD_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".svg", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".zip", ".rar", ".7z", ".mp3",
    ".mp4", ".avi", ".mov", ".wmv", ".txt", ".csv"
)

# 
EMAIL_PATTERN = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
OBFUSCATED_EMAIL_PATTERN = r"([a-zA-Z0-9_.+-]+)\s*\[at\]\s*([a-zA-Z0-9-]+)\s*\[dot\]\s*([a-zA-Z.]+)"



def is_spa_site(url: str, timeout: int = 100, debug=False) -> bool:
    """
        Check if a given url is SPA or not
    """
    try:
        res = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if not res.ok:
            return True  # fallback to SPA if error
        soup = BeautifulSoup(res.text, 'html.parser')

        # Heuristic 1: almost empty body
        body = soup.body
        if not body or len(body.get_text(strip=True)) < 100:
            return True

        # Heuristic 2: common SPA containers
        if soup.find(id="root") or soup.find(id="__next") or soup.find("app"):
            return True

        # Heuristic 3: too much JS, too little content
        scripts = soup.find_all("script")
        if len(scripts) > 20 and len(soup.text.strip()) < 300:
            return True

        # Heuristic 4: SPA framework hint
        js_text = soup.get_text().lower()
        if any(keyword in js_text for keyword in ["react", "vue", "next.js", "angular"]):
            return True

        return False
    except Exception as e:
        if debug:
            print(f"[WARN] SPA detection fallback due to error: {e}")
        return False  # fallback to SPA if request fails
def is_same_domain(base_url, target_url):
    return urlparse(base_url).netloc == urlparse(target_url).netloc

def is_valid_html_link(href: str) -> bool:
    if not href:
        return False
    href = href.lower()
    if href.startswith(("mailto:", "tel:", "#")):
        return False
    if any(href.endswith(ext) for ext in BAD_EXTENSIONS):
        return False
    return True

def is_priority_link(href: str) -> bool:
    return any(keyword in href.lower() for keyword in PRIORITY_KEYWORDS)


