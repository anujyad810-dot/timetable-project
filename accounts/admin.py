from django.contrib import admin

# Register your models here.
from .models import *

admin.site.register(Program)
admin.site.register(Branch)
admin.site.register(Room)
admin.site.register(Subject)
admin.site.register(Teacher)
admin.site.register(TimetableEntry)