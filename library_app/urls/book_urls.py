from django.urls import path
from .. import views
# app_name = 'books'

book_urlpatterns = [
   # ==================== BOOK URLS ====================
    path('books/add/', views.book_add, name='book_add'),
    path('books/sample-csv/', views.sample_csv_download, name='sample_csv_download'),
    
    # Workflow Steps
    # Step 1: Category List (Entry Point)
    path('books/', views.book_list, name='book_list'), 
    # Step 2: Grade/Subject Selector
    path('books/category/<int:category_id>/', views.grade_subject_view, name='grade_subject_view'),
    # Step 3: Final List
    path('books/list/<int:category_id>/', views.final_book_list, name='final_book_list'),

    # CRUD
    path('books/<int:pk>/', views.book_detail, name='book_detail'),
    path('books/<int:pk>/update/', views.book_update, name='book_update'),
    path('books/<int:pk>/delete/', views.book_delete, name='book_delete'),
]



