from django.urls import path
from ..views import manage_students, add_student, student_update, student_delete, get_schools_by_centre, bulk_upload_students, download_sample_excel

student_urlpatterns = [
    path('students/', manage_students, name='manage_students'),
    path('students/add/', add_student, name='add_student'),
    path('students/update/<int:pk>/', student_update, name='student_update'),
    path('students/delete/<int:pk>/', student_delete, name='student_delete'),
    path('get_schools_by_centre/', get_schools_by_centre, name='get_schools_by_centre'),
    path('students/bulk-upload/', bulk_upload_students, name='bulk_upload_students'),  # New path for bulk upload
    path('students/download-sample/', download_sample_excel, name='download_sample_excel'),  # New path for sample Excel
]