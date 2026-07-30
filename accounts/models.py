from django.db import models

class Program(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "programme"

    def __str__(self):
        return self.name

class Branch(models.Model):
    name = models.CharField(max_length=100)
    program = models.ForeignKey(Program, on_delete=models.CASCADE)

    class Meta:
        db_table = "branch"

    def __str__(self):
        return self.name

class Teacher(models.Model):
    name = models.CharField(max_length=120)
    designation = models.CharField(max_length=50, null=True)
    department = models.CharField(max_length=100, null=True)
    email = models.EmailField(max_length=120, null=True)

    class Meta:
        db_table = "teacher"

    def __str__(self):
        return self.name

class Room(models.Model):
    room_name = models.CharField(max_length=100)
    room_type = models.CharField(max_length=50) # 'THEORY' or 'LAB'

    class Meta:
        db_table = "rooms"

    def __str__(self):
        return self.room_name

class Subject(models.Model):
    semester_id = models.IntegerField()
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10) # 'THEORY' or 'LAB'
    weekly_lectures = models.IntegerField(default=3)

    class Meta:
        db_table = "subject"

    def __str__(self):
        return self.name

class TimetableEntry(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    
    semester = models.IntegerField()
    section = models.CharField(max_length=10)
    branch = models.CharField(max_length=50)
    
    # These fields store the "Smart" result
    day = models.CharField(max_length=20, null=True, blank=True)
    time_slot = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "timetable_entry"

    def __str__(self):
        return f"{self.subject.name} - {self.day} ({self.time_slot})"