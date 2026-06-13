from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from datetime import timedelta
from django.http import StreamingHttpResponse,HttpResponseBadRequest
from django.utils import timezone
from rest_framework.parsers import JSONParser
from django_q.tasks import async_task,schedule
from django_q.models import Task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from .models import Lead, Email, CallConversations, Notification
from .core.places.places_api import fetch_places_by_query
from amaya_api.core.email.mail_helper import send_mail_to_lead,get_conversation
from datetime import timedelta
from django.utils import timezone
from django_q.tasks import async_task,schedule
from amaya_api.core.email.mail_helper import send_mail_to_lead,send_email
from amaya_api.core.calls.call_helper import get_audio, sync_conversation_statuses
from .core.tasks.task import fetch_and_scrape_task
from rest_framework.response import Response
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404
from django.db import transaction
import os
import requests

EMAIL_DELAY_IN_MINS = 1
CALL_DELAY_IN_MINS = 1

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
    result_limit = data.get("result_limit", 1)

    if not query:
        return Response(
            {"error": "No Query Given"},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        task_id =  async_task(fetch_and_scrape_task,data,task_name=query.capitalize().replace(',',''),group="Scrape Group")
       
        # response = requests.post(url=f"{SCRAPING_URL}/fetch_and_scrape_places", json=request.data)
        # response.raise_for_status()
        # result = response.json()
        # if not isinstance(result, list) and result['status_code'] == 500:
        #     return Response(
        #         {"error": result['detail']},
        #         status=status.HTTP_500_INTERNAL_SERVER_ERROR
        #     )
        # leads_added = 0
        # # Saving to db
        # for place in result:
        #     place_id = place.get("place_id", "")
        #     if not place_id:
        #         continue
        #     # Check for lead existance
        #     lead = Lead.objects.filter(place_id=place_id).first()

        #     if lead:
        #         # Lead exists maybe update emails
        #         existing_emails = set(Email.objects.filter(business=lead).values_list('email',flat=True))
        #         new_emails = set(place.get('emails', []))
        #         emails_to_add = new_emails - existing_emails
        #         if emails_to_add:
        #             Email.objects.bulk_create(
        #                 [
        #                     Email(business=lead,email=email) for email in emails_to_add
        #                 ]
        #             )

        #     else:
        #         # create new lead
        #         name = place.get("displayName", {}).get('text', '')
        #         types = place.get("types", ["unknown"])
        #         website = place.get("websiteUri", "")
        #         formatted_address = place.get("formattedAddress", "")
        #         opening_hours = place.get("weeklyOpeningHours", "")
        #         national_pn = place.get("nationalPhoneNumber")
        #         international_pn = place.get("internationalPhoneNumber", "")
        #         scrape_error = place.get("scrape_error", "")

        #         lead = Lead(
        #             place_id=place_id,
        #             name=name,
        #             business_types=", ".join(types),
        #             website=website,
        #             formatted_address=formatted_address,
        #             weekly_opening_hours=opening_hours,
        #             national_phone_number=national_pn,
        #             international_phone_number=international_pn,
        #             scrape_error=scrape_error
        #         )
        #         lead.save()

        #         leads_added += 1

        #         emails = place.get('emails', [])
        #         if emails:
        #             for email in emails:
        #                 email_model = Email(
        #                     business=lead,
        #                     email=email
        #                 )
        #                 email_model.save()

        return Response(
            {
                "task_id": task_id,
            },
            status=status.HTTP_202_ACCEPTED
        )
    except Exception as e:
        print(str(e))
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


@api_view(['POST'])
@parser_classes([JSONParser])
def create_lead(request):
    """Manually add a single lead."""
    data = request.data
    name = data.get('name', '').strip()
    if not name:
        return Response({'error': 'Business name is required'}, status=400)

    import uuid
    place_id = data.get('place_id', '').strip() or f"manual-{uuid.uuid4()}"

    lead, created = Lead.objects.get_or_create(
        place_id=place_id,
        defaults={
            'name': name,
            'formatted_address': data.get('address', ''),
            'national_phone_number': data.get('phone', ''),
            'international_phone_number': data.get('international_phone', ''),
            'website': data.get('website', '') or '',
            'business_types': data.get('business_types', ''),
            'description': data.get('description', ''),
        },
    )
    if not created:
        return Response({'error': 'Lead with this place_id already exists'}, status=409)

    # Add emails
    emails = data.get('emails', [])
    if isinstance(emails, str):
        emails = [e.strip() for e in emails.split(',') if e.strip()]
    for email in emails:
        Email.objects.create(business=lead, email=email.strip())

    return Response({
        'place_id': lead.place_id,
        'name': lead.name,
        'created': True,
    }, status=201)


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


def _task_kind(func: str) -> str:
    f = func.lower()
    if 'scrape' in f or 'fetch_and' in f:    return 'scrape'
    if 'mail' in f or 'email' in f:           return 'email'
    if 'call' in f or 'outbound' in f:        return 'call'
    if 'imap' in f or 'replies' in f:        return 'system'
    return 'other'


_FUNC_LABELS = {
    'send_mail_to_lead':         'Send Email',
    'fetch_and_scrape_task':     'Scrape Leads',
    'check_email_replies_task':  'Check Email Replies',
    'make_outbound_call':        'Outbound Call',
    'schedule_outbound_call':    'Outbound Call',
}

# Internal background tasks hidden from the task list
_HIDDEN_FUNCS = {'check_email_replies_task', 'check_call_statuses_task'}

def _readable_name(name: str | None, func: str) -> str:
    """Return a human-readable task name.

    Django Q auto-generates names like 'winner-queen-kitten-alabama' when no
    task_name is given. Detect these and replace with a label derived from the
    func name instead.
    """
    import re
    fn_leaf = func.split('.')[-1] if func else ''
    # Auto-generated: all lowercase letters and hyphens, 3+ segments
    if not name or re.fullmatch(r'[a-z]+(-[a-z]+){2,}', name):
        return _FUNC_LABELS.get(fn_leaf, fn_leaf.replace('_', ' ').title())
    return name


@api_view(['GET'])
def list_tasks(request):
    from django_q.models import Schedule, OrmQ

    # Completed / failed / running tasks (all groups)
    # Tasks with success=None and started >10 min ago are zombie — mark failed
    zombie_cutoff = timezone.now() - timedelta(minutes=10)
    completed = []
    for t in Task.objects.order_by('-stopped').values(
        'id', 'name', 'func', 'started', 'stopped', 'result', 'success', 'attempt_count'
    ):
        # Skip nameless/unidentifiable tasks
        if not t['name'] and not t['func']:
            continue
        if t['success'] is True:
            task_status = 'success'
        elif t['success'] is False:
            task_status = 'failed'
        elif t['started'] and t['started'] < zombie_cutoff:
            task_status = 'failed'
        else:
            task_status = 'running'
        completed.append({
            **t,
            'name': _readable_name(t['name'], t['func'] or ''),
            'kind': _task_kind(t['func'] or ''),
            'status': task_status,
            'result': t['result'] if task_status != 'failed' or t['result'] else
                      ('Task started but never completed (worker crashed)' if t['success'] is None else t['result']),
        })

    # Queued tasks (waiting for a worker to pick them up)
    STALE_MINUTES = 10
    stale_cutoff = timezone.now() - timedelta(minutes=STALE_MINUTES)
    queued = []
    for q in OrmQ.objects.all().order_by('lock'):
        try:
            # OrmQ payloads are SignedPackage strings, not raw pickle/zlib
            payload = q.task
            func = payload.get('func', '') if isinstance(payload, dict) else ''
            if callable(func):
                func = f"{func.__module__}.{func.__name__}"
            name = payload.get('name', '') if isinstance(payload, dict) else ''
        except Exception:
            func, name = '', ''

        # Skip nameless/unidentifiable entries
        if not func and not name:
            continue

        if q.lock and q.lock < stale_cutoff:
            # Worker locked this task but never finished — treat as failed
            q_status = 'failed'
            q_result = f'Task locked {int((timezone.now() - q.lock).total_seconds() // 60)}m ago but never completed (worker may have crashed)'
        elif q.lock:
            q_status = 'running'
            q_result = None
        else:
            q_status = 'scheduled'
            q_result = None

        queued.append({
            'id': f"q-{q.id}",
            'name': _readable_name(name, func),
            'func': func,
            'started': q.lock,
            'stopped': None,
            'result': q_result,
            'success': None,
            'attempt_count': 0,
            'kind': _task_kind(func),
            'status': q_status,
        })

    # Pending scheduled tasks — one-shot (repeats=1) entries whose next_run is
    # more than 30 minutes in the past were never picked up (qcluster was down).
    # Show them as failed rather than perpetually "pending".
    OVERDUE_MINUTES = 30
    overdue_cutoff = timezone.now() - timedelta(minutes=OVERDUE_MINUTES)

    scheduled = []
    for s in Schedule.objects.order_by('next_run').values(
        'id', 'name', 'func', 'next_run', 'repeats'
    ):
        next_run = s['next_run']
        is_recurring = s['repeats'] != 1  # -1 = run forever, >1 = multiple times
        overdue = next_run and next_run < overdue_cutoff and not is_recurring

        scheduled.append({
            'id': f"sched-{s['id']}",
            'name': _readable_name(s['name'], s['func'] or ''),
            'func': s['func'],
            'started': next_run,
            'stopped': None,
            'result': 'Missed scheduled run — qcluster was not running' if overdue else None,
            'success': None,
            'attempt_count': 0,
            'kind': _task_kind(s['func'] or ''),
            'status': 'failed' if overdue else 'scheduled',
        })

    all_tasks = [t for t in completed + queued + scheduled
                 if not any(h in (t.get('func') or '') for h in _HIDDEN_FUNCS)]
    return Response(all_tasks)


@api_view(['POST'])
def purge_stale_schedules(request):
    """Delete one-shot Schedule entries whose next_run is >30 minutes in the past."""
    from django_q.models import Schedule as DQSchedule
    cutoff = timezone.now() - timedelta(minutes=30)
    deleted, _ = DQSchedule.objects.filter(
        repeats=1,
        next_run__lt=cutoff,
    ).delete()
    return Response({'deleted': deleted})


@api_view(['DELETE'])
def delete_email_conversation(request):
    """Remove a specific email address from a lead's email list."""
    place_id = request.query_params.get('place_id', '')
    email_addr = request.query_params.get('email', '')
    if not place_id or not email_addr:
        return Response({'error': 'place_id and email are required'}, status=400)
    lead = get_object_or_404(Lead, place_id=place_id)
    deleted, _ = Email.objects.filter(business=lead, email=email_addr).delete()
    if deleted == 0:
        return Response({'error': 'Email not found'}, status=404)
    if not lead.emails.exists():
        lead.email_sent = False
        lead.save(update_fields=['email_sent'])
    return Response({'success': True})


@api_view(['POST'])
def send_email(request):
    email_rece = request.data.get("to_email","")
    place_id = request.data.get("place_id", "")
    message = request.data.get("message","")
    subject = request.data.get("subject", "") or ""
    lead = get_object_or_404(Lead,place_id=place_id)
    lead_emails = [lead['email'] for lead in lead.emails.all().values('email')]
    print("LEAD EMAILS",lead_emails,email_rece)
    if not email_rece:
        return Response({"detail":"No Email given"},status=status.HTTP_400_BAD_REQUEST)
    if email_rece not in lead_emails:
        return Response({"detail":"No Valid Email given"},status=status.HTTP_400_BAD_REQUEST)
    try:

        from amaya_api.core.email.mail_helper import send_email as send_actual_email
        send_actual_email(email_rece,lead.name,message,subject=subject)
        # Marking the lead as emailed makes a manually-started conversation
        # show up in the email chat sidebar (which lists email_sent leads).
        if not lead.email_sent:
            lead.email_sent = True
            lead.save(update_fields=['email_sent'])
        return Response(
            {"detail": "Email Sent Sucessfully"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        print(f"Email sending error: {str(e)}")
        return Response(
            {"error": f"Failed to send email. Error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ── Email templates ───────────────────────────────────────────────────────────

def _template_dict(t):
    return {
        'id': t.id,
        'name': t.name,
        'category': t.category,
        'subject': t.subject,
        'body': t.body,
        'created_at': t.created_at,
        'updated_at': t.updated_at,
    }


@api_view(['GET', 'POST'])
@parser_classes([JSONParser])
def templates(request):
    if request.method == 'GET':
        qs = EmailTemplate.objects.all()
        return Response([_template_dict(t) for t in qs])

    name = (request.data.get('name') or '').strip()
    body = (request.data.get('body') or '').strip()
    if not name or not body:
        return Response({'error': 'Name and body are required'}, status=status.HTTP_400_BAD_REQUEST)

    category = request.data.get('category', EmailTemplate.Category.GENERAL)
    if category not in EmailTemplate.Category.values:
        category = EmailTemplate.Category.GENERAL

    t = EmailTemplate.objects.create(
        name=name,
        category=category,
        subject=request.data.get('subject', '') or '',
        body=body,
    )
    return Response(_template_dict(t), status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@parser_classes([JSONParser])
def template_detail(request, template_id):
    t = get_object_or_404(EmailTemplate, id=template_id)

    if request.method == 'DELETE':
        t.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    if 'name' in request.data:
        name = (request.data['name'] or '').strip()
        if not name:
            return Response({'error': 'Name cannot be empty'}, status=status.HTTP_400_BAD_REQUEST)
        t.name = name
    if 'body' in request.data:
        t.body = request.data['body'] or ''
    if 'subject' in request.data:
        t.subject = request.data['subject'] or ''
    if 'category' in request.data and request.data['category'] in EmailTemplate.Category.values:
        t.category = request.data['category']
    t.save()
    return Response(_template_dict(t))
@api_view(['POST'])
@parser_classes([JSONParser])
def send_email_to_lead(request):
    place_id = request.data.get("place_id")
    if not place_id:
        return Response({
            "detail": "Missing Lead ID",
            status:status.HTTP_400_BAD_REQUEST
                        })
    lead = Lead.objects.filter(place_id = place_id).first()
    if not lead:
        return Response({
            "detail":"Lead not found"},status=status.HTTP_404_NOT_FOUND)
    
    emails = list(lead.emails.all().values_list("email",flat=True))
    
    if not emails:
        return Response({
            "detail": "Lead has no emails"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        for (idx, email_addr) in enumerate(emails):
            # Check if we have conversation history with this email
            conversation = []
            if lead.email_sent:
                conversation = get_conversation(email_addr)
            
            if conversation:
                # We have conversation history - generate AI reply
                # conversation already has date as ISO string, can pass directly
                payload = {
                    "conversation": conversation,
                    "business_name": lead.name,
                    "our_email": settings.DEFAULT_FROM_EMAIL,
                    "lead_email": email_addr,  # For reliable message direction detection
                    "num_suggestions": 1  # Just get the best suggestion
                }
                
                # Call the AI reply generation endpoint
                response = requests.post(
                    f"{SCRAPING_URL}/generate_reply",
                    json=payload
                )
                response.raise_for_status()
                suggestions = response.json()
                
                if suggestions and len(suggestions) > 0:
                    # Use the first (best) suggestion
                    ai_message = suggestions[0].get("text", "")
                    if ai_message:
                        from amaya_api.core.email.mail_helper import send_email as send_actual_email
                        send_actual_email(email_addr, lead.name, ai_message)
                    else:
                        # AI returned empty text - fallback to template email
                        from amaya_api.core.email.mail_helper import send_mail_to_lead as send_template_email
                        send_template_email(email_addr, lead.name)
                else:
                    # Fallback to template email if no suggestions generated
                    from amaya_api.core.email.mail_helper import send_mail_to_lead as send_template_email
                    send_template_email(email_addr, lead.name)
            else:
                # No conversation history - send initial template email
                from amaya_api.core.email.mail_helper import send_mail_to_lead as send_template_email
                send_template_email(email_addr, lead.name)
            
            lead.email_sent = True
            lead.save()
            
        return Response(
                    {"detail": "Email Sent Successfully"},
                    status=status.HTTP_200_OK
                )

    except requests.RequestException as e:
        print(f"AI reply generation error: {str(e)}")
        return Response(
            {"error": f"Failed to generate AI reply. Error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        print(f"Email sending error: {str(e)}")
        return Response(
            {"error": f"Failed to send email. Error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


CALL_FUNC = 'amaya_api.core.calls.call_helper.schedule_outbound_call'
CALL_DAY_START_HOUR = 9  # UTC hour to start calls on overflow days


def _get_calls_for_date(date) -> int:
    """Calls already made + calls queued for a given date."""
    from django_q.models import Schedule as DQSchedule
    made = CallConversations.objects.filter(created_at=date).count()
    queued = DQSchedule.objects.filter(func=CALL_FUNC, next_run__date=date).count()
    return made + queued


@api_view(['POST'])
@parser_classes([JSONParser])
def call_lead(request):
    """Initiates an outbound call to a lead via ElevenLabs.
    If today's call limit is reached the call is queued for the next
    available day instead of being rejected."""
    from datetime import datetime as dt, timezone as dt_tz

    place_id = request.data.get("place_id")
    if not place_id:
        return Response({"detail": "Missing Lead ID"}, status=status.HTTP_400_BAD_REQUEST)

    lead = Lead.objects.filter(place_id=place_id).first()
    if not lead:
        return Response({"detail": "Lead not found"}, status=status.HTTP_404_NOT_FOUND)

    p_number = lead.international_phone_number
    if not p_number:
        return Response({"detail": "Lead has no phone number"}, status=status.HTTP_404_NOT_FOUND)

    call_daily_limit = getattr(settings, 'CALL_DAILY_LIMIT', 50)
    call_delay_mins = getattr(settings, 'CALL_MIN_DELAY_MINS', 3)
    today = timezone.now().date()
    calls_today = _get_calls_for_date(today)

    if calls_today < call_daily_limit:
        # Capacity today — queue the call as a tracked background task. The
        # task marks call_sent and fires initiated/failed notifications.
        async_task(
            CALL_FUNC,
            lead.place_id,
            p_number,
            task_name=f"Call → {lead.name} ({p_number})",
            group="Call Group",
        )
        return Response({"detail": "Call queued"}, status=status.HTTP_202_ACCEPTED)

    # Today is full — find the next day with capacity (up to 7 days out)
    for day_offset in range(1, 8):
        target_date = today + timedelta(days=day_offset)
        count = _get_calls_for_date(target_date)
        if count < call_daily_limit:
            start = dt(
                target_date.year, target_date.month, target_date.day,
                CALL_DAY_START_HOUR, 0, 0,
                tzinfo=dt_tz.utc,
            )
            next_run = start + timedelta(minutes=call_delay_mins * count)
            schedule(
                CALL_FUNC,
                lead.place_id,
                p_number,
                name=f"Call → {lead.name} ({p_number})",
                schedule_type='O',
                next_run=next_run,
                repeats=1,
            )
            lead.call_sent = True
            lead.save()
            return Response(
                {"detail": f"Daily limit reached — call queued for {target_date.isoformat()}."},
                status=status.HTTP_202_ACCEPTED,
            )

    return Response(
        {"detail": "No call slots available in the next 7 days."},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
@api_view(['GET'])
def get_email_history(request):
    """
        Get the email history of a lead
    """
    place_id = request.query_params.get("place_id", "")
    email = request.query_params.get("email","")
    lead = get_object_or_404(Lead,place_id=place_id)


    emails = list(lead.emails.values_list("email", flat=True))


    # Return empty conversation history if we have never talked to the person
    if not lead.email_sent or email not in emails:
        return Response({
                            'history':[]
                        })
    try:
        conv_history = []
        conv_history=get_conversation(email)
        return Response({
                            "history":conv_history
                        })
    except Exception as e:
        return Response({
                                "error":str(e),
                                
                            },status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_emailed_leads(request):
    leads = Lead.objects.prefetch_related('emails').filter(email_sent=True)

    res = []

    for lead in leads:
        lead_info = model_to_dict(lead)
        lead_info['emails'] = [e.email for e in lead.emails.all()]
        lead_info['created_at'] = lead.created_at
        lead_info['updated_now'] = lead.updated_now
        res.append(lead_info)
    return Response(
        {
            "leads":res
        }
    )    

@api_view(['GET'])
def get_called_leads(request):
    leads = Lead.objects.filter(call_conversations__isnull=False).distinct()
    print(CallConversations.objects.all())
    data = [model_to_dict(lead) for lead in leads]
    return Response({
                        'leads':data
                    })


@api_view(['GET'])
def list_call_conversations(request):
    """All call conversations across all leads, newest first, with lead info.
    Status freshness is maintained by the recurring check_call_statuses_task."""
    conversations = CallConversations.objects.select_related('lead').order_by('-id')
    data = [{
        'id': c.id,
        'conversation_id': c.conversation_id,
        'status': c.status,
        'success': c.success,
        'created_at': c.created_at,
        'place_id': c.lead.place_id,
        'lead_name': c.lead.name,
        'phone': c.lead.international_phone_number or c.lead.national_phone_number or '',
    } for c in conversations]
    return Response({'conversations': data})

@api_view(['GET'])
def get_lead_call_conversations(request):
    """
       Returns an array of conversation had with Lead sorted chronologically, from oldest to newest 
    """
    place_id = request.query_params.get("place_id","")
    lead = get_object_or_404(Lead,place_id=place_id)

    conversations = lead.call_conversations.order_by('-created_at')
    # Refresh pending statuses on view; the recurring poller covers the rest.
    sync_conversation_statuses(conversations)

    data = [model_to_dict(c) for c in conversations]
    return Response({
                        "conversations": data
                    },status=status.HTTP_200_OK)

    pass
@api_view(['GET'])
def get_lead_call_conversation_audio(request):
    """Streams the call audio from ElevenLabs"""

    place_id = request.query_params.get("place_id", "")
    conversation_id = request.query_params.get("conversation_id", "")
    lead = get_object_or_404(Lead,place_id=place_id)

    exists = lead.call_conversations.filter(conversation_id = conversation_id).exists()

    if exists:
        audio_stream = get_audio(conversation_id)
        return StreamingHttpResponse(
            audio_stream,
            content_type="audio/mpeg"
        )
    else:
        return HttpResponseBadRequest("conversation_id is invalid")

@api_view(['POST'])
@parser_classes([JSONParser])
def generate_ai_reply(request):
    """
    Generate AI-powered reply suggestions based on conversation history.
    
    Expected request body:
    {
        "place_id": "abc123",
        "email": "john@business.com",
        "num_suggestions": 3  // optional, defaults to 3
    }
    
    Returns:
    {
        "suggestions": [
            {"id": "uuid-1", "text": "Thank you for your interest..."},
            {"id": "uuid-2", "text": "I'd be happy to help..."},
            {"id": "uuid-3", "text": "Let me provide you with..."}
        ]
    }
    """
    place_id = request.data.get("place_id", "")
    email = request.data.get("email", "")
    num_suggestions = request.data.get("num_suggestions", 3)
    
    if not place_id:
        return Response(
            {"error": "place_id is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not email:
        return Response(
            {"error": "email is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Fetch lead from database
    lead = get_object_or_404(Lead.objects.prefetch_related('emails'), place_id=place_id)
    
    # Verify email belongs to this lead
    lead_emails = list(lead.emails.values_list("email", flat=True))
    if email not in lead_emails:
        return Response(
            {"error": "Email not found for this lead"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get conversation history
    conversation = get_conversation(email)
    
    # Build payload with data from database
    payload = {
        "conversation": conversation,
        "business_name": lead.name,
        "our_email": settings.DEFAULT_FROM_EMAIL,
        "lead_email": email,  # For reliable message direction detection
        "num_suggestions": num_suggestions
    }
    
    try:
        response = requests.post(
            f"{SCRAPING_URL}/generate_reply",
            json=payload
        )
        response.raise_for_status()
        suggestions = response.json()
        
        return Response({
            "suggestions": suggestions
        })
    except requests.RequestException as e:
        return Response(
            {"error": f"Failed to generate AI reply: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_stats(request):
    """Dashboard stats: leads, emails sent, calls made."""
    from django_q.models import Task as DQTask
    emails_sent = DQTask.objects.filter(
        func='amaya_api.core.email.mail_helper.send_mail_to_lead',
        success=True,
    ).count()
    calls_made = CallConversations.objects.count()
    return Response({
        'leads': Lead.objects.count(),
        'emails_sent': emails_sent,
        'calls_made': calls_made,
    })


@api_view(['GET'])
def get_notifications(request):
    """Return the 50 most recent notifications."""
    unread_only = request.query_params.get('unread') == 'true'
    qs = Notification.objects.all()
    if unread_only:
        qs = qs.filter(read=False)
    notifications = list(qs[:50].values(
        'id', 'type', 'title', 'body', 'read', 'created_at', 'metadata',
        'lead_id',
    ))
    return Response(notifications)


@api_view(['POST'])
@parser_classes([JSONParser])
def mark_notifications_read(request):
    """Mark specific notifications as read by id list."""
    ids = request.data.get('ids', [])
    if ids:
        Notification.objects.filter(id__in=ids).update(read=True)
    return Response({'status': 'ok'})


@api_view(['POST'])
def mark_all_notifications_read(request):
    """Mark all unread notifications as read."""
    Notification.objects.filter(read=False).update(read=True)
    return Response({'status': 'ok'})

