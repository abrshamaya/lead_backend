from django.apps import AppConfig


class AmayaApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'amaya_api'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_ensure_imap_schedule, sender=self)


def _ensure_imap_schedule(sender, **kwargs):
    """Register the IMAP poller schedule after migrations complete."""
    try:
        from django_q.models import Schedule
        FUNC = 'amaya_api.core.email.imap_poller.check_email_replies_task'
        if not Schedule.objects.filter(func=FUNC).exists():
            Schedule.objects.create(
                func=FUNC,
                schedule_type=Schedule.MINUTES,
                minutes=5,
                repeats=-1,
            )
    except Exception:
        pass
