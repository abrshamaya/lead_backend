from .email_extractor import extract_emails_recursive
import asyncio
from .spa_email_extractor import spa_extract_emails_recursive
from .utils import is_spa_site


async def scrape_email(URL:str, depth:int=2, debug=False):
    emails =[]
    if URL and is_spa_site(URL):
        if debug:
            print("SPA Website detected, Launching SPA scraper")
        emails =await spa_extract_emails_recursive(URL, depth,debug=debug)
    else:
        if debug:
            print("Static Website detected, Launching Legacy scraper")

        emails = extract_emails_recursive(URL,depth, debug = debug)
        # if no emails found from static site scrapper attempt the spa

        if not emails:
            emails =await spa_extract_emails_recursive(URL, depth, debug=debug)

    if emails and debug:
        print(f"\nFound {len(emails)} email(s):")
        for email in emails:
            print(f" - {email}")
    else:
        if debug:
            print("No emails found.")
    return emails



