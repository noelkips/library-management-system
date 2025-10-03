from django.urls import path
from .. import views
# app_name = 'books'

book_urlpatterns = [
    # ==================== BOOK URLS ====================
    path('books/', views.book_list, name='book_list'),
    path('books/<int:pk>/', views.book_detail, name='book_detail'),
    path('books/add/', views.book_add, name='book_add'),
    path('books/<int:pk>/update/', views.book_update, name='book_update'),
    path('books/<int:pk>/delete/', views.book_delete, name='book_delete'),
    
    # ==================== STUDENT BORROW URLS ====================
    path('borrow/request/<int:book_id>/', views.borrow_request, name='borrow_request'),
    path('my-borrows/', views.my_borrows, name='my_borrows'),
    path('borrow/<int:borrow_id>/cancel/', views.borrow_cancel, name='borrow_cancel'),
    path('borrow/<int:borrow_id>/renew/', views.borrow_renew, name='borrow_renew'),
    
    # ==================== LIBRARIAN BORROW URLS ====================
    path('borrow/requests/', views.borrow_requests_list, name='borrow_requests_list'),
    path('borrow/<int:borrow_id>/issue/', views.borrow_issue, name='borrow_issue'),
    path('borrow/<int:borrow_id>/reject/', views.borrow_reject, name='borrow_reject'),
    path('borrow/active/', views.active_borrows_list, name='active_borrows_list'),
    path('borrow/<int:borrow_id>/receive-return/', views.borrow_receive_return, name='borrow_receive_return'),
    
    # ==================== RESERVATION URLS ====================
    path('reservation/<int:reservation_id>/cancel/', views.reservation_cancel, name='reservation_cancel'),
    path('reservations/', views.reservations_list, name='reservations_list'),
]



