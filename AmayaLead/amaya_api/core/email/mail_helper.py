from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings


def send_mail_to_lead(lead_email, business_name):
    subject = f"Insurance coverage for {business_name}"

    if not lead_email:
        raise Exception("No Email Given")


    print("Attempting to send email...")
    print(f"From: {settings.DEFAULT_FROM_EMAIL}")
    print(f"To: {lead_email}")
    context = {
        "subject": f"Business insurance options for {business_name}",
        "recipient_business_name": f"{business_name}",
        "company_name": "Amaya Insurance Co.",
        "company_address": "500 Market Street, New York, NY 10001",
        "license_number": "LIC-1234567",
        "phone": "+15712772462",
        "product_name": "Business Liability and Property Coverage",
        "logo_url": "https://cdn.securesure.com/logo.png",
        "cta_url": "https://securesure.com/quote/?lead_id=abc123",
        "unsubscribe_url": "https://securesure.com/unsubscribe/",
    }
    plain_msg = render_to_string("email_template.txt", context)
    html_msg = render_to_string("email_template.html", context)

    try:
        send_mail(
            subject=subject,
            message=plain_msg,
            from_email = settings.DEFAULT_FROM_EMAIL,
            recipient_list=[lead_email],
            fail_silently=False,
            html_message=html_msg
        )
    except Exception as e:
        raise Exception("Failed to send email ", str(e))

