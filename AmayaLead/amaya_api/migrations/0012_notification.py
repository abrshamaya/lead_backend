import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("amaya_api", "0011_callconversations"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("email_reply",    "Email Reply"),
                            ("call_initiated", "Call Initiated"),
                            ("call_completed", "Call Completed"),
                            ("call_failed",    "Call Failed"),
                            ("scrape_done",    "Scrape Done"),
                        ],
                        max_length=50,
                    ),
                ),
                ("title",      models.CharField(max_length=255)),
                ("body",       models.TextField(blank=True, default="")),
                ("read",       models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("metadata",   models.JSONField(blank=True, default=dict)),
                (
                    "lead",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="amaya_api.lead",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
