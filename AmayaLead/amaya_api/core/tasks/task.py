import os
import requests
from django.db import transaction
from datetime import timedelta, datetime, timezone as dt_timezone
from django.utils import timezone
from django_q.tasks import schedule
from django_q.models import Task, Schedule
from django.conf import settings
from amaya_api.models import Lead, Email
from amaya_api.core.notifications import notify_scrape_done


if os.getenv("DJANGO_ENV") != "prod":
    SCRAPING_URL = 'http://127.0.0.1:8001'
else:
    SCRAPING_URL = 'http://scraper:8001'

EMAIL_FUNC = 'amaya_api.core.email.mail_helper.send_mail_to_lead'
# Business hours start (UTC). Overflow emails land here on their target day.
EMAIL_DAY_START_HOUR = 9


def get_emails_queued_for_date(date) -> int:
    """Count emails already sent or scheduled for a given calendar date."""
    sent = Task.objects.filter(
        func=EMAIL_FUNC,
        stopped__date=date,
        success=True,
    ).count()
    pending = Schedule.objects.filter(
        func=EMAIL_FUNC,
        next_run__date=date,
    ).count()
    return sent + pending


def fetch_and_scrape_task(data):
    """Fetches places from the scraper service, saves them, and queues outbound
    emails.  Emails that exceed today's daily limit roll over to the next
    available day (up to 7 days ahead) instead of being silently dropped."""

    response = requests.post(url=f"{SCRAPING_URL}/fetch_and_scrape_places", json=data)
    response.raise_for_status()
    result = response.json()

    if not isinstance(result, list) and result.get('status_code') == 500:
        raise Exception(result.get('Error Scraping'))

    daily_limit = getattr(settings, 'EMAIL_DAILY_LIMIT', 400)
    delay_mins = getattr(settings, 'EMAIL_MIN_DELAY_MINS', 2)
    now = timezone.now()  # captured at execution time, not import time

    # Per-day slot counters initialised from the DB so concurrent runs and
    # previous runs in the same day are all accounted for.
    day_counts: dict = {}

    def _count_for(d):
        if d not in day_counts:
            day_counts[d] = get_emails_queued_for_date(d)
        return day_counts[d]

    def _next_run_for(email_addr, name) -> datetime | None:
        """
        Find the earliest day that still has capacity, reserve one slot in the
        in-memory counter, and return the datetime to fire the email.
        Returns None if no slot found within 7 days.
        """
        for day_offset in range(7):
            d = now.date() + timedelta(days=day_offset)
            count = _count_for(d)
            if count >= daily_limit:
                continue

            # Reserve the slot before scheduling so the next email in this
            # loop gets the next slot, not the same one.
            day_counts[d] = count + 1

            if day_offset == 0:
                # Today — continue staggering from the current moment
                return now + timedelta(minutes=delay_mins * (count + 1))
            else:
                # Future day — start from EMAIL_DAY_START_HOUR UTC
                start = datetime(
                    d.year, d.month, d.day,
                    EMAIL_DAY_START_HOUR, 0, 0,
                    tzinfo=dt_timezone.utc,
                )
                return start + timedelta(minutes=delay_mins * count)

        return None  # no capacity in the next 7 days

    leads_added = 0

    with transaction.atomic():
        for place in result:
            place_id = place.get("place_id", "")
            if not place_id:
                continue

            lead = Lead.objects.filter(place_id=place_id).first()

            if lead:
                existing_emails = set(
                    Email.objects.filter(business=lead).values_list('email', flat=True)
                )
                new_emails = set(place.get('emails', []))
                emails_to_add = new_emails - existing_emails
                if emails_to_add:
                    Email.objects.bulk_create(
                        [Email(business=lead, email=e) for e in emails_to_add]
                    )
            else:
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
                    scrape_error=scrape_error,
                )
                lead.save()
                leads_added += 1

                emails = place.get('emails', [])
                if emails:
                    Email.objects.bulk_create(
                        [Email(business=lead, email=e) for e in emails]
                    )

                for email_addr in emails:
                    next_run = _next_run_for(email_addr, name)
                    if next_run is None:
                        print(
                            f"[task] No email slots in the next 7 days — "
                            f"skipping {email_addr} for {name}."
                        )
                        continue
                    schedule(
                        EMAIL_FUNC,
                        email_addr,
                        name,
                        schedule_type='O',
                        next_run=next_run,
                        repeats=1,
                    )

    task_name = data.get("query", "unknown")
    try:
        notify_scrape_done(leads_added, task_name)
    except Exception as e:
        print(f"[task] Failed to create scrape notification: {e}")

    return f"{leads_added} New Leads"
