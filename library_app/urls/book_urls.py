# library_app/urls/book_urls.py
from django.urls import path

# IMPORT THE MISSING VIEW HERE
from .. import views

book_urlpatterns = [
    path('books/',  views.book_list, name='book_list'),
    path('books/ajax/load-schools-modal/',  views.ajax_load_schools_modal, name='ajax_load_schools_modal'),
    path('books/school/<int:school_id>/catalog/',  views.school_catalog, name='school_catalog'),
    path('books/school/<int:school_id>/grade/<int:grade_id>/',  views.grade_book_list, name='grade_book_list'),
    path('books/add/',  views.book_add, name='book_add'),
    path('books/<int:pk>/update/',  views.book_update, name='book_edit'),
    path('book/<int:pk>/update/', views.book_update, name='book_update'),
    path('books/<int:pk>/delete/',  views.book_delete, name='book_delete'),
    path('books/<int:pk>/',  views.book_detail, name='book_detail'),
    path('books/borrows/<int:pk>/approve/',  views.borrow_approve, name='borrow_approve'),
    path('books/sample-csv/',  views.sample_csv_download, name='sample_csv_download'),
    path('books/ajax/load-schools/',  views.ajax_load_schools, name='ajax_load_schools'),
    path('books/ajax/load-subjects/',  views.ajax_load_subjects, name='ajax_load_subjects'),
    path('books/add/confirmation/', views.book_add_confirmation, name='book_add_confirmation'),
]