
# scraper_worker.py

import asyncio
import sys
import json
from scraper import scrape_email


async def main():
    website = sys.argv[1]
    depth = int(sys.argv[2])
    retries = int(sys.argv[3])
    tmp_file = sys.argv[4] if len(sys.argv) == 5 else "tmp_file.txt"

    for attempt in range(1, retries + 1):
        try:
            emails = await scrape_email(website, depth=depth, tmp_file=tmp_file,debug=False)
            print(json.dumps({"status": "ok", "emails": emails}),flush=True)
            return  # Success → exit main
        except Exception as e:
            if attempt == retries:
                # On last attempt → print error and exit
                print(json.dumps({"status": "error", "error": str(e)}),flush=True)
                sys.exit(1)

if __name__ == '__main__':
    # loop = asyncio.get_event_loop()
    # asyncio.set_event_loop(loop)
    # loop.run_until_complete(main())
    asyncio.run(main())

