import os
import requests
from django.db import transaction
import time
from amaya_api.models import Lead,Email
if os.getenv("DJANGO_ENV") != "prod":
    SCRAPING_URL = 'http://127.0.0.1:8001'
else:
    SCRAPING_URL = 'http://scraper:8001'

def fetch_and_scrape_task(data):
    """
        Fetches places and scrapes them
    """
    response = requests.post(url=f"{SCRAPING_URL}/fetch_and_scrape_places", json=data)

    response.raise_for_status()
    result = response.json()

    if not isinstance(result, list) and result['status_code'] == 500:
        raise Exception(result.get('Error Scraping'))
    leads_added = 0

    with transaction.atomic():
        for place in result:
            place_id = place.get("place_id", "")
            if not place_id:
                continue
            # Check for lead existance
            lead = Lead.objects.filter(place_id=place_id).first()

            if lead:
                # Lead exists maybe update emails
                existing_emails = set(Email.objects.filter(business=lead).values_list('email',flat=True))
                new_emails = set(place.get('emails', []))
                emails_to_add = new_emails - existing_emails
                if emails_to_add:
                    Email.objects.bulk_create(
                        [
                            Email(business=lead,email=email) for email in emails_to_add
                        ]
                    )

            else:
                # create new lead
                name = place.get("displayName", {}).get('text', '')
                types = place.get("types", ["unknown"])
                website = place.get("websiteUri", "")
                formatted_address = place.get("formattedAddress", "")
                opening_hours = place.get("weeklyOpeningHours", "")
                national_pn = place.get("nationalPhoneNumber")
                international_pn = place.get("internationalPhoneNumber", "")
                scrape_error = place.get("scrape_error", "")

                lead = Lead(
                    place_id=place_id,
                    name=name,
                    business_types=", ".join(types),
                    website=website,
                    formatted_address=formatted_address,
                    weekly_opening_hours=opening_hours,
                    national_phone_number=national_pn,
                    international_phone_number=international_pn,
                    scrape_error=scrape_error
                )
                lead.save()

                leads_added += 1

                emails = place.get('emails', [])
                if emails:
                    for email in emails:
                        email_model = Email(
                            business=lead,
                            email=email
                        )
                        email_model.save()
    return f"{leads_added} New Leads"
def long_task():

    time.sleep(10)

