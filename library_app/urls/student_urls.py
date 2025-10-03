from django.urls import path
from ..views import student_list, student_add, student_update, student_delete, get_schools_by_centre


# app_name = 'students'

student_urlpatterns = [
    path('students/', student_list, name='student_list'),
    path('students/add/', student_add, name='student_add'),
    path('students/update/<int:pk>/', student_update, name='student_update'),
    path('students/delete/<int:pk>/', student_delete, name='student_delete'),
    path('get_schools_by_centre/', get_schools_by_centre, name='get_schools_by_centre'),
]

