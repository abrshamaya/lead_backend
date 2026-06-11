from django.apps import AppConfig


class AmayaApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'amaya_api'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_ensure_recurring_schedules, sender=self)


def _ensure_recurring_schedules(sender, **kwargs):
    """Register recurring background schedules after migrations complete."""
    try:
        from django_q.models import Schedule

        RECURRING = [
            # (func, minutes)
            ('amaya_api.core.email.imap_poller.check_email_replies_task', 5),
            ('amaya_api.core.calls.call_helper.check_call_statuses_task', 2),
        ]
        for func, minutes in RECURRING:
            if not Schedule.objects.filter(func=func).exists():
                Schedule.objects.create(
                    func=func,
                    schedule_type=Schedule.MINUTES,
                    minutes=minutes,
                    repeats=-1,
                )
    except Exception:
        pass
