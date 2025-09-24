from fastapi import FastAPI
from playwright.sync_api import sync_playwright

app = FastAPI()

def scrape_sync(url: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=40000)
        title = page.title()
        browser.close()
        return title

@app.get("/test")
async def test(url: str):
    # you can await other async tasks if needed
    title = scrape_sync(url)  # sync Playwright
    return {"title": title}
