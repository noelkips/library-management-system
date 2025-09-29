from django.urls import path
from ..views import book_list, book_add, book_update, book_delete

# app_name = 'books'

book_urlpatterns = [
    path('books/', book_list, name='book_list'),
    path('books/add/', book_add, name='book_add'),
    path('books/update/<int:pk>/', book_update, name='book_update'),
    path('books/delete/<int:pk>/', book_delete, name='book_delete'),
]