from django.db import migrations


SEED_TEMPLATES = [
    {
        "name": "Cold Reach — Intro",
        "category": "cold_reach",
        "subject": "Business insurance options for {business_name}",
        "body": (
            "Hi {business_name} team,\n\n"
            "I'm with Mahfuz Insurance Agency — we help local businesses like yours "
            "get the right liability and property coverage without overpaying.\n\n"
            "Would you be open to a quick chat this week to see if we can save you money "
            "on your current policy?\n\n"
            "Best regards,\n"
            "Mahfuz Insurance Agency\n"
            "703-212-9131"
        ),
    },
    {
        "name": "Follow-up — No Reply",
        "category": "follow_up",
        "subject": "Following up — insurance for {business_name}",
        "body": (
            "Hi {business_name} team,\n\n"
            "Just following up on my note from last week. I'd still love to put together "
            "a no-obligation quote for {business_name}.\n\n"
            "Is there a good time to connect for 10 minutes?\n\n"
            "Best regards,\n"
            "Mahfuz Insurance Agency\n"
            "703-212-9131"
        ),
    },
    {
        "name": "Re-engagement",
        "category": "re_engage",
        "subject": "Still looking for better coverage, {business_name}?",
        "body": (
            "Hi {business_name} team,\n\n"
            "It's been a little while since we last connected. Insurance rates have shifted "
            "recently, and many businesses are finding real savings by reviewing their policy.\n\n"
            "Happy to run a free comparison whenever you're ready.\n\n"
            "Best regards,\n"
            "Mahfuz Insurance Agency"
        ),
    },
    {
        "name": "Thank You",
        "category": "thank_you",
        "subject": "Thank you, {business_name}!",
        "body": (
            "Hi {business_name} team,\n\n"
            "Thank you for taking the time to speak with us. We're glad to have you covered.\n\n"
            "If anything comes up, don't hesitate to reach out.\n\n"
            "Warm regards,\n"
            "Mahfuz Insurance Agency"
        ),
    },
]


def seed(apps, schema_editor):
    EmailTemplate = apps.get_model("amaya_api", "EmailTemplate")
    for t in SEED_TEMPLATES:
        EmailTemplate.objects.get_or_create(name=t["name"], defaults=t)


def unseed(apps, schema_editor):
    EmailTemplate = apps.get_model("amaya_api", "EmailTemplate")
    EmailTemplate.objects.filter(name__in=[t["name"] for t in SEED_TEMPLATES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("amaya_api", "0014_emailtemplate"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
