from django.apps import AppConfig


class AmayaApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'amaya_api'

    def ready(self):
        # Schedule the IMAP reply poller to run every 5 minutes.
        # Guard against double-registration (e.g. dev reloader forks).
        try:
            from django_q.models import Schedule
            FUNC = 'amaya_api.core.email.imap_poller.check_email_replies_task'
            if not Schedule.objects.filter(func=FUNC).exists():
                Schedule.objects.create(
                    func=FUNC,
                    schedule_type=Schedule.MINUTES,
                    minutes=5,
                    repeats=-1,  # run forever
                )
        except Exception:
            # DB may not be set up yet (e.g. during migrations)
            pass
