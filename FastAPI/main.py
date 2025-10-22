# fastapi_server.py
from fastapi import FastAPI, HTTPException
from places.places_api import fetch_places_by_query
from AI.filter_emails import filter_emails
from pydantic import BaseModel
import sys
import subprocess
import json
from lead_types import HashablePlace
from typing import List
import traceback
app = FastAPI()
SCRAPER_TIMEOUT = 100

class ScrapeRequest(BaseModel):
    url: str


class FetchRequest(BaseModel):
    query: str
    result_limit: int


@app.post("/fetch_and_scrape_places")
def fetch_and_scrape_places(req: FetchRequest):
    query = req.query
    limit = req.result_limit if req.result_limit else 1
    fetch_res = []
    try:
        fetch_res: List[HashablePlace] = fetch_places_by_query(query, limit)
    except Exception as e:
        tb = traceback.extract_tb(sys.exc_info()[2])[-1]
        filename = tb.filename
        line_number = tb.lineno
        return HTTPException(status_code=500, detail=f"{filename}:{line_number} {str(e)}")
    res = []
    if fetch_res:
        res = [place.to_dict() for place in fetch_res]


    for place in res:
        url = place['websiteUri']
        place['emails'] = []
        if url:
            try:
                # Creating a scraping sub process
                proc = subprocess.Popen(
                   args=[sys.executable, '-m', 'scraper_worker', url, '1', '5'],
                   text=True,
                   stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE
                )
                try:
                    out, err = proc.communicate(timeout=SCRAPER_TIMEOUT)
                    result = json.loads(out)
                    if result.get("status", '') == 'ok':
                        try:
                            place['emails'] = filter_emails(place['displayName']['text'],result['emails'])
                        except Exception as e:
                            print("Error during validation", e)
                            place['emails'] = result['emails']
                    else:
                        place['scrape_error'] = "Website Refused"
                except subprocess.TimeoutExpired:
                    proc.kill()
                    place['emails'] = []
                    place['scrape_error'] = "Timeout Exceeded"
            except Exception as e:
                exc_type = type(e).__name__
                # Get traceback info (last call frame where exception happened)
                tb = traceback.extract_tb(sys.exc_info()[2])[-1]
                filename = tb.filename
                line_number = tb.lineno
                return HTTPException(status_code=500, detail=f"{filename}:{line_number} {str(e)}")
        else:
            place['scrape_error'] = 'No Website Found'
    return res


class PlacesRequest(BaseModel):
    places:list[list[str]]
@app.post("/scrape_places")
def scrape_places(req:PlacesRequest):

    res = []
    places = req.places

    for place in places:
        place_id, place_url = place
        emails =[]
        if place_url:
            try:
                # Creating a scraping sub process
                proc = subprocess.Popen(
                   args=[sys.executable, '-m', 'scraper_worker', place_url, '1', '5'],
                   text=True,
                   stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE
                )
                try:
                    out, err = proc.communicate(timeout=SCRAPER_TIMEOUT)
                    result = json.loads(out)
                    if result.get("status", '') == 'ok':
                        emails = result['emails']

                except subprocess.TimeoutExpired:
                    emails =[]
            except Exception as e:
                emails =[]

        res.append((place_id, emails))


    return res

class EmailsReq(BaseModel):
    business_name:str
    emails: list[str]


@app.post("/filter_email")
def api_filter_emails(req: EmailsReq):
    emails = req.emails
    name = req.business_name

    validated = []

    try:
        validated = filter_emails(name, emails)
    except Exception as e:
        print("Error during validation", e)
        return []
    return validated


class WebsiteReq(BaseModel):
    url: str


@app.post("/scrape")
def scrape_website(req:WebsiteReq):
    res = []
    url = req.url
    if url:
        try:
            proc = subprocess.Popen(
                args = [sys.executable, '-m', 'scraper_worker', url,'1', '5'],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            try:
                out, err = proc.communicate(timeout=SCRAPER_TIMEOUT)
                print(out, err)
                result = json.loads(out)
                if result.get('status', '')=='ok':
                    emails = result['emails']
                    res.append(emails)
                else:
                    return HTTPException(status_code=500, detail=f"Failed to scrape with error: {result['error']}")
            except Exception as e:
                res = []
                return HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            return HTTPException(status_code=500, detail=str(e))
            res = []

    return res
