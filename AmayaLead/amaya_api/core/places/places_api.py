import requests
import os
from amaya_api.core.lead_types import DisplayName, HashablePlace, Place

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

GOOGLE_PLACES_API = os.getenv("GOOGLE_PLACES_API", "xxx")


headers = {
    'Content-Type': 'application/json',
    'X-Goog-Api-Key': GOOGLE_PLACES_API,
    'X-Goog-FieldMask': 'places.displayName,places.websiteUri,places.nationalPhoneNumber,places.internationalPhoneNumber,places.formattedAddress,places.regularOpeningHours,nextPageToken'
}


def fetch_places_by_query(query: str, result_limit: int = 2):

    payload = {
        'textQuery': query,
        'maxResultCount': result_limit
    }

    response = requests.post(url=TEXT_SEARCH_URL, json=payload, headers=headers)

    if response.status_code == 200:
        result = response.json()
        places = result.get('places', [])

        res_places = []

        for place in places:
            name_info =  place.get('displayName', {})
            place_info: Place = {}


            display_info:DisplayName = {
                'text': name_info.get('text', ''),
                'languageCode': name_info.get('languageCode', '')
            }
            place_info['displayName'] = display_info

            opening_hour = ", ".join(list(place.get("regularOpeningHours", {}).get("weekdayDescriptions", [])))
            place_info['weeklyOpeningHours'] = opening_hour

            place_info['formattedAddress'] = place.get("formattedAddress", '')

            place_info['internationalPhoneNumber'] = place.get('internationalPhoneNumber','')
            place_info['nationalPhoneNumber'] = place.get('nationalPhoneNumber', '')
            place_info['websiteUri'] = place.get('websiteUri', '')



            res_places.append(HashablePlace(place_info))


        return res_places
