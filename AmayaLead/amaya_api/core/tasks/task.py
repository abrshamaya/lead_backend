import os
import requests
from django.db import transaction
import uuid
from datetime import timedelta
from django.utils import timezone
from django_q.tasks import async_task,schedule
from amaya_api.core.email.mail_helper import send_mail_to_lead
from amaya_api.core.calls.call_helper import make_outbound_call
import time


EMAIL_DELAY_IN_MINS = 1
CALL_DELAY_IN_MINS = 2

now = timezone.now()

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
    bussiness_name_phone_pairs = []

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
                if(international_pn):
                    bussiness_name_phone_pairs.append([name,international_pn])

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
                # Emailing me for now
                for idx,email in enumerate(emails):
                    schedule("amaya_api.core.email.mail_helper.send_mail_to_lead",
                    email,name,
                    schedule_type='O',next_run=now+timedelta(minutes=EMAIL_DELAY_IN_MINS*(idx+1)),repeats=1)
                # for idx,pairs in enumerate(bussiness_name_phone_pairs):
                #     b_name = pairs[0]
                #     # phone_number = pairs[1]
                #     # using our phone number for now
                #     schedule("amaya_api.core.calls.call_helper.make_outbound_call",
                #     b_name,"+15712772462",
                #     schedule_type='O',next_run=now+timedelta(minutes=CALL_DELAY_IN_MINS*(idx+1)),repeats=1)

    return f"{leads_added} New Leads"
