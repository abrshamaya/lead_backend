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
    scrape_error = models.CharField(max_length=512,blank=True , default = None)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_now = models.DateTimeField(auto_now=True)



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
        INPROGRESS = 'in-progress','inprogress'
        PROCESSING = 'processing','Processing'
        DONE = 'Done','done'
        FAILED = 'failed','Failed'
    sucess = models.BooleanField(default=False)
    status = models.CharField(max_length=64, choices=Status.choices,default=Status.INITIATED)
    conversation_id = models.CharField(max_length=128,default='')
    call_sid = models.CharField(max_length=128,default='')
