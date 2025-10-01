from django.urls import path
from ..views import issue_book, issue_list

issue_urlpatterns = [
    path('issue-book/', issue_book, name='issue_book'),
    path('issue-list/', issue_list, name='issue_list'),
]