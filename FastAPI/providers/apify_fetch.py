import os
import time
import requests
import uuid
import logging
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
ACTOR_ID = os.environ.get("APIFY_ACTOR_ID", "compass~crawler-google-places")

def map_apify_place(p: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map Apify Google Maps scraper result to our internal schema.
    
    Args:
        p: Raw Apify place data
        
    Returns:
        Mapped place data matching our schema
    """
    return {
        "placeId": p.get("placeId", uuid.uuid4()),
        "business_name": p.get("title", ""),
        "websiteUri": p.get("website"),
        "phone_number": p.get("phone",''),
        "international_phone_number": p.get('phoneUnformatted', ''),
        "address": p.get("address"),
        "opening_hours": p.get("openingHours"),
        "business_types": [p.get("category")] if p.get("category") else [],
    }

def fetch_places_by_query_via_apify(search_term: str, state: str = "",county:str="", zipcode: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch places using Apify Google Maps Scraper.
    
    Args:
        search_term: Business type or name to search for
        state: State name (optional)
        zipcode: ZIP code (optional)
        county: Count name (optional)
        limit: Maximum number of places to return
        
    Returns:
        List of mapped place dictionaries
        
    Raises:
        RuntimeError: If APIFY_TOKEN is missing or run fails
        requests.RequestException: If API calls fail
    """
    if not APIFY_TOKEN:
        raise RuntimeError("APIFY_TOKEN is not set but USE_APIFY=true")
    
    if not search_term.strip():
        raise ValueError("search_term cannot be empty")
    
    # The compass/crawler-google-places actor returns far more results when the
    # business term and the location are passed SEPARATELY — the term goes in
    # searchStringsArray and the area goes in locationQuery, which the actor
    # geocodes and tiles to collect up to maxCrawledPlacesPerSearch. Gluing the
    # state onto the term (e.g. "restaurant Virginia") makes Google treat it as a
    # single loose text search and return only a handful of results.
    search_strings = [search_term.strip()]

    # Build the location string from the most specific parts available.
    location_parts = []
    if county:
        location_parts.append(f"{county} County")
    if state:
        location_parts.append(state)
    location_query = ", ".join(location_parts)
    if location_query:
        location_query = f"{location_query}, USA"
    # A bare ZIP geocodes reliably on its own and is more specific than a state.
    if zipcode:
        location_query = f"{zipcode}, USA"

    payload = {
        "searchStringsArray": search_strings,
        "maxCrawledPlacesPerSearch": int(limit),
        "language": "en",
    }
    if location_query:
        payload["locationQuery"] = location_query

    logger.info(f"Starting Apify run with search: {search_strings}, location: '{location_query}', limit: {limit}")
    
    try:
        # 1) Start run
        start_url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs?token={APIFY_TOKEN}"
        start_response = requests.post(start_url, json=payload, timeout=30)
        start_response.raise_for_status()
        
        run_data = start_response.json()
        run_id = run_data["data"]["id"]
        logger.info(f"Started Apify run with ID: {run_id}")
        
        # 2) Poll status — abort after 3 minutes
        status = "RUNNING"
        max_polls = 90  # 3 minutes max (90 * 2 seconds)
        poll_count = 0
        status_data = None

        while status in ("RUNNING", "READY", "PAUSED", "RESTARTING") and poll_count < max_polls:
            time.sleep(2)
            poll_count += 1

            status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}"
            status_response = requests.get(status_url, timeout=20)
            status_response.raise_for_status()

            status_data = status_response.json()
            status = status_data["data"]["status"]

            if poll_count % 15 == 0:  # Log every 30s
                logger.info(f"Apify run {run_id} status: {status} (poll {poll_count})")

        if status != "SUCCEEDED":
            # Abort the run if it's still going
            if status in ("RUNNING", "READY"):
                try:
                    requests.post(f"https://api.apify.com/v2/actor-runs/{run_id}/abort?token={APIFY_TOKEN}", timeout=10)
                    logger.info(f"Aborted stale Apify run {run_id}")
                except Exception:
                    pass
            error_msg = f"Apify run timed out or failed (status: {status})"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        dataset_id = status_data["data"]["defaultDatasetId"]
        logger.info(f"Apify run succeeded. Dataset ID: {dataset_id}")
        
        # 3) Fetch results
        data_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_TOKEN}&clean=true&format=json"
        data_response = requests.get(data_url, timeout=60)
        data_response.raise_for_status()
        
        items = data_response.json()
        logger.info(f"Retrieved {len(items)} items from Apify dataset")
        
        # Map results to our schema
        mapped_places = [map_apify_place(p) for p in items]
        
        logger.info(f"Successfully mapped {len(mapped_places)} places")
        return mapped_places
        
    except requests.RequestException as e:
        logger.error(f"Apify API request failed: {e}")
        raise
    except KeyError as e:
        logger.error(f"Unexpected Apify response format: {e}")
        raise RuntimeError(f"Unexpected Apify response format: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in Apify integration: {e}")
        raise
