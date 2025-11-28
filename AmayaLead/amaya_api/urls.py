from django.urls import path
from . import views

urlpatterns = [
    path("query_places", views.fetch_places, name="index"),
    path("fetch_and_scrape", views.fetch_and_scrape, name="index"),
    path("filter_email", views.filter_email, name="index"),
    path("leads", views.list_leads, name='list leads'),
    path("leads/<str:place_id>", views.delete_lead, name="delete lead"),
    path("retry_scrape", views.retry_scrape, name='retry scrape'),
    path("leads_count", views.leads_count, name='count of leads'),
    path("filter_email", views.filter_email, name="index"),
    path("tasks", views.list_tasks, name="List Tasks"),
    path("call_lead", views.call_lead, name="Call Lead"),
    path("email_lead", views.send_email_to_lead, name="Email Lead"),
    path("emailed_leads",views.get_emailed_leads,name="Get all emailed leads"),
    path("called_leads",views.get_called_leads, name="Called Leads"),
    path("email_history", views.get_email_history, name="get conversation history")
]
