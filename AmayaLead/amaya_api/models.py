from django.db import models


class Lead(models.Model):
    place_id = models.CharField(max_length=512, default='', unique=True, null=False)
    name = models.CharField(max_length=512, null=False)
    description = models.TextField(blank=True, default='')
    business_types = models.CharField(max_length=1024, blank=True, default = '')
    website = models.URLField(max_length=1024, blank=True, null=True, default='')
    formatted_address = models.TextField(blank=True, null=True, default = '')
    weekly_opening_hours = models.TextField(blank=True, null=True, default='')
    national_phone_number = models.CharField(max_length=128, null=True,blank=True, default='')
    international_phone_number = models.CharField(max_length=128,null=True,blank=True, default='')
    scrape_error = models.CharField(max_length=512,blank=True , default = '')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_now = models.DateTimeField(auto_now=True)
    email_sent = models.BooleanField(default=False)
    call_sent = models.BooleanField(default=False)



# Allowed values:
# initiated
# in-progress
# processing
# done
# failed
class Email(models.Model):
    business = models.ForeignKey(Lead, on_delete = models.CASCADE,related_name='emails')
    email = models.EmailField(blank=True, default = '')

class CallStatus(models.Model):
    class Status(models.TextChoices):
        INITIATED = 'initiated', 'Initiated'
        INPROGRESS = 'in-progress', 'In Progress'
        PROCESSING = 'processing', 'Processing'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'

    success = models.BooleanField(default=False)
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.INITIATED
    )
    conversation_id = models.CharField(max_length=128, default='')
    call_sid = models.CharField(max_length=128, default='')

    def __str__(self):
        return f"{self.status} ({self.conversation_id})"

class CallConversations(models.Model):
    class Status(models.TextChoices):
        INITIATED = 'initiated', 'Initiated'
        INPROGRESS = 'in-progress', 'In Progress'
        PROCESSING = 'processing', 'Processing'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'
    lead = models.ForeignKey(Lead, on_delete = models.CASCADE,related_name='call_conversations')

    success = models.BooleanField(default=False)
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.INITIATED
    )
    conversation_id = models.CharField(max_length=128, default='')
    call_sid = models.CharField(max_length=128, default='')
    created_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"{self.status} ({self.conversation_id})"
    @classmethod
    def is_valid_status(cls, status:str) -> bool:
        return status in cls.Status.values


class Notification(models.Model):
    class Type(models.TextChoices):
        EMAIL_REPLY     = 'email_reply',     'Email Reply'
        CALL_INITIATED  = 'call_initiated',  'Call Initiated'
        CALL_COMPLETED  = 'call_completed',  'Call Completed'
        CALL_FAILED     = 'call_failed',     'Call Failed'
        SCRAPE_DONE     = 'scrape_done',     'Scrape Done'

    type       = models.CharField(max_length=50, choices=Type.choices)
    lead       = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    title      = models.CharField(max_length=255)
    body       = models.TextField(blank=True, default='')
    read       = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # Extra data: email address, conversation_id, leads_added, etc.
    metadata   = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.type}] {self.title}"
