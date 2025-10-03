from django.urls import path
from ..views import issue_book, issue_list, return_book

issue_urlpatterns = [
    path('issue-book/', issue_book, name='issue_book'),
    path('issue-list/', issue_list, name='issue_list'),
    path('return/<int:issue_id>/', return_book, name='return_book'),
]