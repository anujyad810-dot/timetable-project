from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse

# Models
from .models import Subject, Teacher, Room, TimetableEntry, Branch, ScheduleSlot

# ReportLab PDF Imports
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
import random

# --- Helper Function for Clash Checking ---

def is_slot_available(teacher_id, room_id, branch, semester, section, day, time_slot):
    """
    Validates if a specific time slot is strictly available across the entire university.
    """
    # CONSTRAINT 1: The Teacher Check
    if ScheduleSlot.objects.filter(requirement__teacher_id=teacher_id, day=day, time_slot=time_slot).exists():
        return False

    # CONSTRAINT 2: The Room Check
    if ScheduleSlot.objects.filter(requirement__room_id=room_id, day=day, time_slot=time_slot).exists():
        return False

    # CONSTRAINT 3: The Student Group Check
    if ScheduleSlot.objects.filter(
        requirement__branch=branch, requirement__semester=semester,
        requirement__section=section, day=day, time_slot=time_slot
    ).exists():
        return False

    return True

# --- Account & Role Management ---

def splash_page(request):
    return render(request, 'accounts/splash_page.html')

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
        
        # Check if the user clicked a history button
        if request.POST.get('action') == 'view_history':
            return redirect("timetable_view")
            
        # IMPORTANT: This forces non-teachers to skip the input page!
        if request.session.get('role') == "teacher":
            return redirect("teacher_input")
        else:
            return redirect("timetable_view")
    
    # FETCH HISTORY
    generated_timetables = TimetableEntry.objects.exclude(day__isnull=True).values(
        'branch', 'semester', 'section'
    ).distinct()

    branches = Branch.objects.values('name')

    return render(request, "accounts/program_select.html", {
        "generated_timetables": generated_timetables,
        "branches": branches
    })


# --- Teacher Input Section ---

@login_required
def teacher_input(request):
    semester = request.session.get("semester")
    section = request.session.get("section")
    branch = request.session.get("branch")

    subjects = Subject.objects.filter(semester_id=semester)
    teachers = Teacher.objects.all()
    rooms = Room.objects.all()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            subject_id = request.POST.get("subject")
            teacher_id = request.POST.get("teacher_id")
            room_id = request.POST.get("room_id")
            duration = int(request.POST.get("duration", 1))

            if subject_id and teacher_id and room_id:
                for _ in range(duration):
                    TimetableEntry.objects.create(
                        subject_id=subject_id, teacher_id=teacher_id, room_id=room_id,
                        semester=semester, section=section, branch=branch
                    )
                messages.success(request, f"Added {duration} lectures successfully.")

        elif action == "reset":
            TimetableEntry.objects.filter(semester=semester, section=section, branch=branch).delete()
            # Also clear the generated slots for this class
            ScheduleSlot.objects.filter(requirement__semester=semester, requirement__section=section, requirement__branch=branch).delete()
            messages.success(request, "Requirements and timetable cleared for this section.")
            return redirect("teacher_input")

        elif action == "generate":
            if not TimetableEntry.objects.filter(semester=semester, section=section, branch=branch).exists():
                messages.error(request, "Please add subjects first!")
            else:
                # Triggers the new backtracking engine
                return redirect("generate_timetable")

    entries = TimetableEntry.objects.filter(semester=semester, section=section, branch=branch)

    return render(request, "accounts/teacher_input.html", {
        "subjects": subjects, "teachers": teachers, "rooms": rooms,
        "entries": entries, "semester": semester, "branch": branch, "section": section
    })


# --- The Smart Generator (Production Grade) ---

@login_required
def generate_timetable(request):
    sem = request.session.get("semester")
    sec = request.session.get("section")
    br = request.session.get("branch")

    # 1. Clear previous drafts for this specific class
    ScheduleSlot.objects.filter(requirement__semester=sem, requirement__section=sec, requirement__branch=br).delete()

    # 2. Fetch all requirements created in teacher_input
    entries = list(TimetableEntry.objects.filter(semester=sem, section=sec, branch=br))
    
    # 3. Optimize processing order: LABs first (hardest to place), then Theory
    entries.sort(key=lambda x: (1 if x.subject.type == 'LAB' else 0), reverse=True)

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    time_slots = ["10-11", "11-12", "12-1", "2-3", "3-4", "4-5", "5-6"]
    lab_pairs = [("10-11", "11-12"), ("11-12", "12-1"), ("2-3", "3-4"), ("3-4", "4-5"), ("4-5", "5-6")]

    # 4. The Recursive Backtracking Algorithm
    def solve(index):
        if index == len(entries):
            return True 

        entry = entries[index]
        is_lab = entry.subject.type == "LAB"

        for day in days:
            # Soft Constraint: Prefer not to teach the same theory subject twice in one day
            if not is_lab and ScheduleSlot.objects.filter(
                requirement__subject=entry.subject, requirement__branch=br, 
                requirement__semester=sem, requirement__section=sec, day=day
            ).exists():
                continue

            if is_lab:
                # Labs require two consecutive, clash-free slots
                for s1, s2 in lab_pairs:
                    if is_slot_available(entry.teacher.id, entry.room.id, br, sem, sec, day, s1) and \
                       is_slot_available(entry.teacher.id, entry.room.id, br, sem, sec, day, s2):
                        
                        slot1 = ScheduleSlot.objects.create(requirement=entry, day=day, time_slot=s1)
                        slot2 = ScheduleSlot.objects.create(requirement=entry, day=day, time_slot=s2)
                        
                        if solve(index + 1):
                            return True
                        
                        slot1.delete()
                        slot2.delete()
            else:
                # Theory requires a single clash-free slot
                for slot in time_slots:
                    if is_slot_available(entry.teacher.id, entry.room.id, br, sem, sec, day, slot):
                        
                        slot_obj = ScheduleSlot.objects.create(requirement=entry, day=day, time_slot=slot)
                        
                        if solve(index + 1):
                            return True
                            
                        slot_obj.delete()

        return False

    success = solve(0)

    if success:
        messages.success(request, "Enterprise-grade timetable generated perfectly with zero clashes!")
    else:
        messages.error(request, "Algorithm failed to find a clash-free combination. You lack available teachers/rooms for this workload.")
        
    return redirect("timetable_view")


# --- Output Views ---

def timetable_view(request):
    sem, sec, br = request.session.get("semester"), request.session.get("section"), request.session.get("branch")
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    time_slots = ["10-11", "11-12", "12-1", "1-2", "2-3", "3-4", "4-5", "5-6"]

    timetable = {day: {slot: "Free" for slot in time_slots} for day in days}
    for d in days: timetable[d]["1-2"] = "LUNCH"

    # Query ScheduleSlot for the generated final matrix
    drafts = ScheduleSlot.objects.filter(requirement__semester=sem, requirement__section=sec, requirement__branch=br)

    for draft in drafts:
        req = draft.requirement
        text = f"{req.subject.name}\n{req.teacher.name}\n({req.room.room_name})"
        timetable[draft.day][draft.time_slot] = text

    return render(request, "accounts/timetable_view.html", {
        "timetable": timetable, "days": days, "time_slots": time_slots
    })


def download_timetable_pdf(request):
    sem = request.session.get("semester")
    sec = request.session.get("section")
    br = request.session.get("branch")

    if not all([sem, sec, br]):
        return HttpResponse("Please select Program/Branch/Semester first.")

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{br}_Sem{sem}_{sec}_Timetable.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()
    
    cell_style = ParagraphStyle(
        'TableCell', parent=styles['Normal'],
        fontSize=8, leading=10, alignment=TA_CENTER 
    )
    
    elements.append(Paragraph(f"MADHAV INSTITUTE OF TECHNOLOGY & SCIENCE, GWALIOR", styles['Title']))
    elements.append(Paragraph(f"Class Timetable: {br} | Semester: {sem} | Section: {sec}", styles['Heading2']))
    elements.append(Paragraph("<br/><br/>", styles['Normal']))

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    time_slots = ["10-11", "11-12", "12-1", "1-2", "2-3", "3-4", "4-5", "5-6"]
    
    data = [[Paragraph(f"<b>Day / Time</b>", cell_style)] + [Paragraph(f"<b>{slot}</b>", cell_style) for slot in time_slots]]
    
    drafts = ScheduleSlot.objects.filter(requirement__semester=sem, requirement__section=sec, requirement__branch=br)

    for day in days:
        row = [Paragraph(f"<b>{day}</b>", cell_style)]
        for slot in time_slots:
            if slot == "1-2":
                row.append(Paragraph("<b>LUNCH</b>", cell_style))
                continue
            
            draft = drafts.filter(day=day, time_slot=slot).first()
            if draft:
                req = draft.requirement
                cell_text = f"<b>{req.subject.name}</b><br/>{req.teacher.name}<br/>({req.room.room_name})"
                row.append(Paragraph(cell_text, cell_style))
            else:
                row.append(Paragraph("Free", cell_style))
        data.append(row)

    table = Table(data, colWidths=[65] + [82] * len(time_slots))
    style = TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ])
    
    for row_idx, row_data in enumerate(data):
        for col_idx, cell_value in enumerate(row_data):
            if hasattr(cell_value, 'text') and "LUNCH" in cell_value.text:
                style.add('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), colors.lightsalmon)

    table.setStyle(style)
    elements.append(table)
    doc.build(elements)
    return response