from django.contrib import admin
# Make sure ALL models are imported here!
from .models import Program, Branch, Teacher, Room, Subject, TimetableEntry, ScheduleSlot

# Register your models here so they show up in the Django Admin panel
admin.site.register(Program)
admin.site.register(Branch)
admin.site.register(Teacher)
admin.site.register(Room)
admin.site.register(Subject)
admin.site.register(TimetableEntry)
admin.site.register(ScheduleSlot) # Added the new draft table!