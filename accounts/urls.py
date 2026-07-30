from django.urls import path
from . import views

urlpatterns = [
    path('', views.splash_page, name='home'), 
    path('role-select/', views.role_select_page, name='role_select_page'),
    # path('', views.role_select_page, name='role_select_page'),
    path('select-role/<str:role>/', views.select_role, name='select_role'),
    path("teacher/login/", views.teacher_login, name="teacher_login"),
    path("program/select/", views.program_select, name="program_select"),
    path("teacher/input/", views.teacher_input, name="teacher_input"),
    path("generate/", views.generate_timetable, name="generate_timetable"),
    path('timetable/', views.timetable_view, name='timetable_view'),
    path('download-pdf/', views.download_timetable_pdf, name='download_pdf'),
]