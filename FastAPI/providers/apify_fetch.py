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
        "phone_number": p.get("phoneUnformatted"),
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
    
    # Build search strings array
    search_strings = []
    if search_term and zipcode:
        search_strings.append(f"{search_term} {zipcode}".strip())
    if search_term and state:
        search_strings.append(f"{search_term} {state}".strip())
    if not search_strings:
        # Fallback to just the term to avoid empty actor run
        search_strings = [search_term.strip()]
    
    # Remove duplicates while preserving order
    search_strings = list(dict.fromkeys(search_strings))
    
    payload = {
        "searchStringsArray":[search_term] ,
        "locationQuery": f"{state}, USA",
        "postalCode": zipcode,
        "state": state,
        "county": county,
        "maxCrawledPlacesPerSearch": int(limit),
        "language": "en",
        "includeRawResults": False,
        "checkClosedPlaces": False,
    }
    
    logger.info(f"Starting Apify run with search strings: {search_strings}, limit: {limit}")
    
    try:
        # 1) Start run
        start_url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs?token={APIFY_TOKEN}"
        start_response = requests.post(start_url, json=payload, timeout=30)
        start_response.raise_for_status()
        
        run_data = start_response.json()
        run_id = run_data["data"]["id"]
        logger.info(f"Started Apify run with ID: {run_id}")
        
        # 2) Poll status
        status = "RUNNING"
        max_polls = 300  # 10 minutes max (300 * 2 seconds)
        poll_count = 0
        
        while status in ("RUNNING", "READY", "PAUSED", "RESTARTING") and poll_count < max_polls:
            time.sleep(2)
            poll_count += 1
            
            status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}"
            status_response = requests.get(status_url, timeout=20)
            status_response.raise_for_status()
            
            status_data = status_response.json()
            status = status_data["data"]["status"]
            
            if poll_count % 30 == 0:  # Log every minute
                logger.info(f"Apify run {run_id} status: {status} (poll {poll_count})")
        
        if status != "SUCCEEDED":
            error_msg = f"Apify run failed with status: {status}"
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
