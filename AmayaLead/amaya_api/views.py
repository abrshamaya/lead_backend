from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser
from .models import Lead, Email
from .core.places.places_api import fetch_places_by_query
from rest_framework.response import Response
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404
from django.db import transaction
import os
import requests

# Fast API Scraping servel URL

if os.getenv("DJANGO_ENV") != "prod":
    SCRAPING_URL = 'http://127.0.0.1:8001'
else:
    SCRAPING_URL = 'http://scraper:8001'


@api_view(['POST'])
@parser_classes([JSONParser])
def fetch_places(request):
    """Fetches places from given query"""
    data = request.data
    query = data.get("query", "")
    result_limit = data.get("max_limit", 1)

    if not query:
        return Response(
            {"error": "No Query Given"},
            status=status.HTTP_400_BAD_REQUEST
        )

    res = fetch_places_by_query(query, result_limit)
    res = [place.to_dict() for place in res]
    return Response(
        {"result": res},
        status=status.HTTP_200_OK,
    )


@api_view(['POST'])
@parser_classes([JSONParser])
def fetch_and_scrape(request):
    """
        Fetches places and scrapes them
    """
    data = request.data
    query = data.get("query", "")
    searchTerm = data.get("searchTerm", "")
    zipcode = data.get("zipcode", "")
    state = data.get("state", "")

    if not query:
        return Response(
            {"error": "No Query Given"},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        response = requests.post(url=f"{SCRAPING_URL}/fetch_and_scrape_places", json=request.data)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, list) and result['status_code'] == 500:
            return Response(
                {"error": result['detail']},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        leads_added = 0
        # Saving to db
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

        return Response(
            {
                "result": "Sucess",
                "inserted": leads_added
            },
            status=status.HTTP_201_CREATED
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
def retry_scrape(req):
    data = req.data
    places = data.get('places')

    found_emails =0

    if not places:
        return Response({"error": "no places given"}, status=status.HTTP_400_BAD_REQUEST)
    db_places = list(Lead.objects.filter(place_id__in=places))

    payload = [[str(p.place_id), str(p.website)] for p in db_places]
    result = []

    try:
        response = requests.post(url=f"{SCRAPING_URL}/scrape_places", json={
                                     "places": payload
                                 })
        response.raise_for_status()

        result = response.json()

        for lead, res_place in zip(db_places, result):
            new_emails = set(res_place[1])
            existing_emails = set(Email.objects.filter(business=lead).values_list('email',flat=True))
            emails_to_add = new_emails - existing_emails
            if emails_to_add:
                found_emails +=1
                Email.objects.bulk_create(
                    [
                        Email(business=lead,email=email) for email in emails_to_add
                    ]
                )
                lead.scrape_error = ""
                lead.save()
    except Exception as e:
        return Response(
            {
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response(
        {
            "found": found_emails
        },
        status=status.HTTP_200_OK
    )



@api_view(['GET'])
def list_leads(request):
    leads = Lead.objects.prefetch_related('emails').all()

    res = []

    for lead in leads:
        lead_info = model_to_dict(lead)
        lead_info['emails'] = [e.email for e in lead.emails.all()]
        lead_info['created_at'] = lead.created_at
        lead_info['updated_now'] = lead.updated_now
        res.append(lead_info)
    return Response(
        res
    )
@api_view(['GET'])
def leads_count(request):
    count = Lead.objects.count()

    return Response({
                        'count': count
                    })


@api_view(['DELETE'])
def delete_lead(req, place_id):
    lead = get_object_or_404(Lead, place_id=place_id)

    lead.delete()

    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
def filter_email(request):
    # 1. Get the single Lead object
    place_id = request.data.get("place_id", "")
    lead = get_object_or_404(Lead.objects.prefetch_related('emails'), place_id=place_id)

    # 2. Extract existing emails
    lead_emails = [e.email for e in lead.emails.all()]

    # 3. Get business name from request
    business_name = lead.name 
    if not business_name:
        return Response({"error": "business_name is required"}, status=400)

    # 4. Prepare payload for filtering service
    payload = {
        "business_name": business_name,
        "emails": lead_emails
    }

    # 5. Call the internal API to filter emails
    try:
        resp = requests.post(f"{SCRAPING_URL}/filter_email", json=payload)
        resp.raise_for_status()
        filtered_emails = resp.json()  # expected to be a list of valid emails
    except requests.RequestException as e:
        return Response({"error": f"Failed to call filter service: {str(e)}"}, status=500)

    # 6. Update lead emails in DB
    with transaction.atomic():
        # Clear existing emails
        lead.emails.all().delete()

        # Re-create filtered emails
        for email in filtered_emails:
            lead.emails.create(email=email)

    # 7. Return simple success status
    return Response({"status": "success"})
