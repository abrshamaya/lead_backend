from fastapi import FastAPI, HTTPException
from places.places_api import fetch_places_by_query
from AI.filter_emails import filter_emails
from providers.apify_fetch import fetch_places_by_query_via_apify
from pydantic import BaseModel
import sys
import tempfile
import logging
from typing import Optional
import os
import uuid
import subprocess
from dotenv import load_dotenv
import json
from lead_types import HashablePlace
from typing import List
import traceback
app = FastAPI()

SCRAPER_TIMEOUT = 100

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def normalize_hours(data):
    result_parts = []
    for entry in data:
        day = entry['day']
        hours = entry['hours']
        if 'closed' in hours.lower():
            formatted = f"{day}: Closed"
        else:
            formatted = f"{day}: 11:00 AM – 11:00 PM"
        result_parts.append(formatted)
    return ', '.join(result_parts)

load_dotenv()
USE_APIFY = os.getenv("USE_APIFY", "true").lower() == "true"


class ScrapeRequest(BaseModel):
    url: str


class FetchRequest(BaseModel):
    searchTerm:str
    query: str
    result_limit: int
    state:Optional[str] = None
    zipcode:Optional[str] = None
    county:Optional[str] = None

@app.post("/fetch_and_scrape_places")
def fetch_and_scrape_places(req: FetchRequest):
    searchTerm = req.searchTerm
    query = req.query
    limit = req.result_limit if req.result_limit else 1
    state = req.state if req.state else ""
    county = req.county if req.county else ""
    zipcode = req.zipcode if req.zipcode else ""
    fetch_res = []
    try:
        if USE_APIFY:
            logger.info(f"Using Apify provider for query: '{searchTerm}', state: '{state}', county: {county}, zipcode: '{zipcode}', limit: {limit}")
            apify_results = fetch_places_by_query_via_apify(searchTerm, state,county, zipcode, limit)
            fetch_res = []
            for place_data in apify_results:
                # Create a HashablePlace-compatible object
                place_obj = HashablePlace({
                    'displayName': {'text': place_data.get('business_name', ''), 'languageCode': 'en'},
                    'place_id': place_data.get("placeId"),
                    'websiteUri': place_data.get('websiteUri',''),
                    'nationalPhoneNumber': place_data.get('phone_number', ''),
                    'internationalPhoneNumber': place_data.get('international_phone_number',''),
                    'formattedAddress': place_data.get('address', ''),
                    'types': place_data.get('business_types', []),
                    'weeklyOpeningHours': normalize_hours(place_data.get('opening_hours', '')),
                })
                fetch_res.append(place_obj)
        else:
            fetch_res: List[HashablePlace] = fetch_places_by_query(query, limit)
    except Exception as e:
        tb = traceback.extract_tb(sys.exc_info()[2])[-1]
        return HTTPException(
            status_code=500,
            detail=f"{tb.filename}:{tb.lineno} {str(e)}"
        )

    res = [place.to_dict() for place in fetch_res]

    logger.info(f"The length of places found is {len(res)}")
    for place in res:
        url = place.get('websiteUri')
        place['emails'] = []

        if url:
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            tmp_filename = tmp_file.name
            tmp_file.close()

            try:
                proc = subprocess.Popen(
                    args=[sys.executable, '-m', 'scraper_worker', url, '1', '5', tmp_filename],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                try:
                    out, err = proc.communicate(timeout=SCRAPER_TIMEOUT)
                    result = json.loads(out)

                    if result.get("status") == "ok":
                        try:
                            place['emails'] = result['emails']
                        except Exception as e:
                            print("Error during validation:", e)
                            place['emails'] = result['emails']
                    else:
                        with open(tmp_filename, 'r', encoding='utf-8') as f:
                            emails = [line.strip() for line in f if line.strip()]
                        place['emails'] = emails
                        if not emails:
                            place['scrape_error'] = result.get("error", "No Email Found")

                except subprocess.TimeoutExpired:
                    proc.kill()
                    with open(tmp_filename, 'r', encoding='utf-8') as f:
                        emails = [line.strip() for line in f if line.strip()]
                    place['emails'] = emails
                    if not emails:
                        place['scrape_error'] = "Timeout Exceeded"

                except Exception as e:
                    proc.kill()
                    with open(tmp_filename, 'r', encoding='utf-8') as f:
                        emails = [line.strip() for line in f if line.strip()]
                    place['emails'] = emails
                    if not emails:
                        place['scrape_error'] = str(e)

            except Exception as e:
                tb = traceback.extract_tb(sys.exc_info()[2])[-1]
                return HTTPException(
                    status_code=500,
                    detail=f"{tb.filename}:{tb.lineno} {str(e)}"
                )

            finally:
                if os.path.exists(tmp_filename):
                    os.remove(tmp_filename)
        else:
            place['scrape_error'] = 'No Website Found'

    return res

class PlacesRequest(BaseModel):
    places: list[list[str]]

@app.post("/scrape_places")
def scrape_places(req: PlacesRequest):
    res = []
    places = req.places

    for place in places:
        place_id, place_url = place
        emails = []

        if place_url:
            # Create a temporary file for the scraper to store results
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            tmp_filename = tmp_file.name
            tmp_file.close()

            try:
                proc = subprocess.Popen(
                    args=[sys.executable, '-m', 'scraper_worker', place_url, '1', '5', tmp_filename],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                try:
                    print("started")
                    out, err = proc.communicate(timeout=2*SCRAPER_TIMEOUT)
                    result = json.loads(out)
                    print(result, err)

                    if result.get("status") == "ok":
                        emails = result['emails']
                    else:
                        with open(tmp_filename, 'r', encoding='utf-8') as f:
                            emails = [line.strip() for line in f if line.strip()]

                except subprocess.TimeoutExpired:
                    proc.kill()
                    with open(tmp_filename, 'r', encoding='utf-8') as f:
                        emails = [line.strip() for line in f if line.strip()]

                except Exception:
                    proc.kill()
                    with open(tmp_filename, 'r', encoding='utf-8') as f:
                        emails = [line.strip() for line in f if line.strip()]

            finally:
                if os.path.exists(tmp_filename):
                    os.remove(tmp_filename)

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
            tmp_filename = f"{uuid.uuid4()}.txt"
            proc = subprocess.Popen(
                args = [sys.executable, '-m', 'scraper_worker', url,'1', '5', tmp_filename],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            try:
                out, err = proc.communicate(timeout=SCRAPER_TIMEOUT)
                result = json.loads(out)
                if result.get('status', '')=='ok':
                    emails = result['emails']
                    res.append(emails)
                else:
                    proc.kill()
                    with open(tmp_filename, 'r', encoding='utf-8') as f:
                        res = [line.strip() for line in f if line.strip()]
                    if not res:
                        return HTTPException(status_code=500, detail=f"Failed to scrape with error: {result['error']}")
            except subprocess.TimeoutExpired:
                # Read the results of the temp file for any left overs
                proc.kill()
                with open(tmp_filename, 'r', encoding='utf-8') as f:
                    res = [line.strip() for line in f if line.strip()]
            except Exception as e:
                res = []
                return HTTPException(status_code=500, detail=str(e))
            finally:
                os.remove(tmp_filename)
        except Exception as e:
            return HTTPException(status_code=500, detail=str(e))
            res = []

    return res
