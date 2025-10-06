from django.urls import path
from .. import views


borrow_urlpatterns = [
   # User-facing borrow views
      # User-facing borrow views
    path('request/<int:book_id>/', views.borrow_request, name='borrow_request'),
    path('my-borrows/', views.my_borrows, name='my_borrows'),
    path('cancel/<int:borrow_id>/', views.borrow_cancel, name='borrow_cancel'),
    path('renew/<int:borrow_id>/', views.borrow_renew, name='borrow_renew'),

    # Librarian-facing borrow views
    path('requests/', views.borrow_requests_list, name='borrow_requests_list'),
    path('issue/<int:borrow_id>/', views.borrow_issue, name='borrow_issue'),
    path('reject/<int:borrow_id>/', views.borrow_reject, name='borrow_reject'),
    path('active/', views.active_borrows_list, name='active_borrows_list'),
    path('receive-return/<int:borrow_id>/', views.borrow_receive_return, name='borrow_receive_return'),
    path('history/', views.all_borrows_history, name='all_borrows_history'),

    # Reservation views
    path('reservations/cancel/<int:reservation_id>/', views.reservation_cancel, name='reservation_cancel'),
    path('reservations/', views.reservations_list, name='reservations_list'),
    path('reserve/<int:book_id>/', views.reserve_book, name='reserve_book'),

    # Teacher-facing views
    path('teacher/my-books/', views.teacher_my_books, name='teacher_my_books'),
    path('teacher/issue-to-student/<int:borrow_id>/', views.teacher_issue_to_student, name='teacher_issue_to_student'),
    path('teacher/manage-book/<int:borrow_id>/', views.teacher_manage_book, name='teacher_manage_book'),
    path('teacher/receive-return/<int:issue_id>/', views.teacher_receive_return, name='teacher_receive_return'),
    path('teacher/all-issues/', views.teacher_all_issues, name='teacher_all_issues'),
    path('teacher/issue-update/<int:issue_id>/', views.teacher_issue_update, name='teacher_issue_update'),
]