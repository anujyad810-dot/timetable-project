from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Subject, Teacher, Room, TimetableEntry
import random
from django.http import HttpResponse



# Views.py
def splash_page(request):
    return render(request, 'accounts/splash_page.html') # Ensure this path is correct
# --- Account & Role Management ---

def role_select_page(request):
    return render(request, 'accounts/role_select.html')

def select_role(request, role):
    request.session['role'] = role
    return redirect("teacher_login") if role == "teacher" else redirect("program_select")

def teacher_login(request):
    if request.method == "POST":
        u, p = request.POST.get("username"), request.POST.get("password")
        user = authenticate(request, username=u, password=p)
        if user and user.groups.filter(name="teacher_role").exists():
            login(request, user)
            return redirect("program_select")
        messages.error(request, "Invalid credentials or not a teacher")
    return render(request, "accounts/teacher_login.html")

def program_select(request):
    if request.method == "POST":
        request.session['program'] = request.POST.get('program')
        request.session['branch'] = request.POST.get('branch')
        request.session['semester'] = request.POST.get('semester')
        request.session['section'] = request.POST.get('section')
        return redirect("teacher_input") if request.session.get('role') == "teacher" else redirect("timetable_view")
    return render(request, "accounts/program_select.html")

# --- Teacher Input Section ---

@login_required
def teacher_input(request):
    # Get current context from session
    semester = request.session.get("semester")
    section = request.session.get("section")
    branch = request.session.get("branch")

    # Fetch data for dropdowns
    subjects = Subject.objects.filter(semester_id=semester)
    teachers = Teacher.objects.all()
    rooms = Room.objects.all()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            subject_id = request.POST.get("subject")
            teacher_id = request.POST.get("teacher_id")
            room_id = request.POST.get("room_id")
            # FIX: Get duration from the POST form input, not the database
            duration = int(request.POST.get("duration", 1))

            if subject_id and teacher_id and room_id:
                # Create 'n' number of entries based on user input duration
                for _ in range(duration):
                    TimetableEntry.objects.create(
                        subject_id=subject_id,
                        teacher_id=teacher_id,
                        room_id=room_id,
                        semester=semester,
                        section=section,
                        branch=branch
                    )
                messages.success(request, f"Added {duration} lectures successfully.")

        elif action == "reset":
            TimetableEntry.objects.filter(
                semester=semester, section=section, branch=branch
            ).delete()
            messages.success(request, "Requirements cleared for this section.")
            return redirect("teacher_input")

        elif action == "generate":
            # Check if any subjects were added before generating
            if not TimetableEntry.objects.filter(semester=semester, section=section, branch=branch).exists():
                messages.error(request, "Please add subjects first!")
            else:
                return redirect("generate_timetable")

    # Fetch added entries to show in the table below the form
    entries = TimetableEntry.objects.filter(semester=semester, section=section, branch=branch)

    return render(request, "accounts/teacher_input.html", {
        "subjects": subjects,
        "teachers": teachers,
        "rooms": rooms,
        "entries": entries
    })

# --- The Smart Generator ---
import random
from django.db.models import Count
from django.shortcuts import redirect
from django.contrib import messages

@login_required
def generate_timetable(request):
    # 1. INITIAL SETUP & CLEANUP
    sem, sec, br = request.session.get("semester"), request.session.get("section"), request.session.get("branch")
    TimetableEntry.objects.filter(semester=sem, section=sec, branch=br).update(day=None, time_slot=None)

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    time_slots = ["10-11", "11-12", "12-1", "1-2", "2-3", "3-4", "4-5", "5-6"]

    # ✅ NEW: Random start per day (10, 11, or 12), always ends at 5-6
    day_start_index = {day: random.choice([0, 1, 2]) for day in days}

    subjects_placed_today = {day: [] for day in days}
    lab_placed_today = {day: False for day in days}
    labs_placed_this_week = []

    # 2. PRIORITY SORTING
    all_entries = list(TimetableEntry.objects.filter(semester=sem, section=sec, branch=br))

    def get_priority(entry):
        global_load = TimetableEntry.objects.filter(teacher=entry.teacher).count()
        type_weight = 100 if entry.subject.type == "LAB" else 0
        return type_weight + global_load

    all_entries.sort(key=get_priority, reverse=True)

    lab_entries = [e for e in all_entries if e.subject.type == "LAB"]
    theory_entries = [e for e in all_entries if e.subject.type != "LAB"]

    # --- PHASE 1: ANCHOR LAB PLACEMENT ---
    for entry in lab_entries:
        if entry.subject.name in labs_placed_this_week:
            continue

        placed = False
        shuffled_days = days[:]
        random.shuffle(shuffled_days)

        for day in shuffled_days:
            if lab_placed_today[day]:
                continue

            start_idx = day_start_index[day]  # ✅ Respect this day's start

            for i in range(start_idx, len(time_slots) - 1):
                s1, s2 = time_slots[i], time_slots[i + 1]
                if s1 == "1-2" or s2 == "1-2":
                    continue

                t_busy = (
                    TimetableEntry.objects.filter(teacher=entry.teacher, day=day, time_slot__icontains=s1).exists() or
                    TimetableEntry.objects.filter(teacher=entry.teacher, day=day, time_slot__icontains=s2).exists()
                )

                if not t_busy:
                    entry.day, entry.time_slot = day, f"{s1} & {s2}"
                    entry.save()
                    lab_placed_today[day] = True
                    labs_placed_this_week.append(entry.subject.name)
                    subjects_placed_today[day].append(entry.subject.name)
                    placed = True
                    break
            if placed:
                break

    # --- PHASE 2: VERTICAL SLOT-FIRST THEORY FILLING ---
    slots_filled_today = {day: (1 if lab_placed_today[day] else 0) for day in days}

    for slot_idx, slot in enumerate(time_slots):
        if slot == "1-2":
            continue

        balanced_days = sorted(days, key=lambda d: slots_filled_today[d])

        for day in balanced_days:
            # ✅ Skip slots before this day's random start
            if slot_idx < day_start_index[day]:
                continue

            if TimetableEntry.objects.filter(semester=sem, section=sec, branch=br, day=day, time_slot__icontains=slot).exists():
                continue

            for entry in theory_entries:
                if entry.day:
                    continue
                if entry.subject.name in subjects_placed_today[day]:
                    continue

                t_busy = TimetableEntry.objects.filter(teacher=entry.teacher, day=day, time_slot__icontains=slot).exists()

                if not t_busy:
                    entry.day, entry.time_slot = day, slot
                    entry.save()
                    subjects_placed_today[day].append(entry.subject.name)
                    slots_filled_today[day] += 1
                    break

# --- PHASE 3: COMPACT — Zero gaps between classes ---
    for day in days:
        start_idx = day_start_index[day]

        # 1. Find which slots labs are occupying on this day (they are immovable anchors)
        lab_slots = set()
        day_lab_entries = TimetableEntry.objects.filter(
            semester=sem, section=sec, branch=br, day=day, subject__type="LAB"
        )
        for lab in day_lab_entries:
            for s in lab.time_slot.split(" & "):
                lab_slots.add(s.strip())

        # 2. Build the list of "fillable" slots for this day:
        #    - Must be at or after this day's random start
        #    - Must not be lunch (1-2)
        #    - Must not be occupied by a lab
        fillable_slots = [
            slot for idx, slot in enumerate(time_slots)
            if idx >= start_idx
            and slot != "1-2"
            and slot not in lab_slots
        ]

        # 3. Fetch all theory entries already placed on this day
        theory_entries_today = list(
            TimetableEntry.objects.filter(
                semester=sem, section=sec, branch=br, day=day
            ).exclude(subject__type="LAB")
        )

        # 4. Sort them by their current slot order so relative order is preserved
        slot_order = {s: i for i, s in enumerate(time_slots)}
        theory_entries_today.sort(key=lambda e: slot_order.get(e.time_slot, 99))

        # 5. Re-assign them consecutively into fillable_slots — no gaps possible
        for i, entry in enumerate(theory_entries_today):
            if i < len(fillable_slots):
                entry.time_slot = fillable_slots[i]
                entry.save()

    messages.success(request, "Timetable Generated & Optimized!")
    return redirect("timetable_view")

def timetable_view(request):
    sem, sec, br = request.session.get("semester"), request.session.get("section"), request.session.get("branch")
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    time_slots = ["10-11", "11-12", "12-1", "1-2", "2-3", "3-4", "4-5", "5-6"]

    timetable = {day: {slot: "Free" for slot in time_slots} for day in days}
    for d in days: timetable[d]["1-2"] = "LUNCH"

    # Pull from DB (so Student Role can see it)
    entries = TimetableEntry.objects.filter(semester=sem, section=sec, branch=br).exclude(day__isnull=True)

    for e in entries:
        text = f"{e.subject.name}\n{e.teacher.name}\n({e.room.room_name})"
        if "&" in e.time_slot:
            for s in e.time_slot.split(" & "): timetable[e.day][s] = text
        else:
            timetable[e.day][e.time_slot] = text

    return render(request, "accounts/timetable_view.html", {
        "timetable": timetable, "days": days, "time_slots": time_slots
    })
    from django.http import HttpResponse
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet

def download_timetable_pdf(request):
    # 1. Get the context from the session
    sem = request.session.get("semester")
    sec = request.session.get("section")
    br = request.session.get("branch")

    if not all([sem, sec, br]):
        return HttpResponse("Please select Program/Branch/Semester first.")

    # 2. Prepare the Response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{br}_Sem{sem}_{sec}_Timetable.pdf"'

    # 3. Setup PDF Document
    doc = SimpleDocTemplate(response, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    elements.append(Paragraph(f"MADHAV INSTITUTE OF TECHNOLOGY & SCIENCE, GWALIOR", styles['Title']))
    elements.append(Paragraph(f"Class Timetable: {br} | Semester: {sem} | Section: {sec}", styles['Heading2']))
    elements.append(Paragraph("<br/><br/>", styles['Normal']))

    # 4. Define Grid
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    time_slots = ["10-11", "11-12", "12-1", "1-2", "2-3", "3-4", "4-5", "5-6"]
    
    # Header Row
    data = [["Day / Time"] + time_slots]

    # 5. Fetch Data from DB
    entries = TimetableEntry.objects.filter(semester=sem, section=sec, branch=br).exclude(day__isnull=True)

    for day in days:
        row = [day]
        for slot in time_slots:
            if slot == "1-2":
                row.append("LUNCH")
                continue
            
            # Find the entry for this specific day and slot
            # Note: icontains is used to handle LAB slots like "10-11 & 11-12"
            entry = entries.filter(day=day, time_slot__icontains=slot).first()
            if entry:
                row.append(f"{entry.subject.name}\n{entry.teacher.name}")
            else:
                row.append("Free")
        data.append(row)

    # 6. Create Table & Style
    table = Table(data, colWidths=[80] + [85] * len(time_slots))
    
    style = TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke), # Header Background
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
    ])
    
    # Add highlighting for Lunch
    for row_idx, row_data in enumerate(data):
        for col_idx, cell_value in enumerate(row_data):
            if cell_value == "LUNCH":
                style.add('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), colors.lightsalmon)

    table.setStyle(style)
    elements.append(table)

    # 7. Build PDF
    doc.build(elements)
    return response