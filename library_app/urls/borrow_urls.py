from django.urls import path
from ..views import borrow_add, borrow_list


borrow_urlpatterns = [
    path('borrow/add/', borrow_add, name='borrow_add'),
    path('borrow/list/', borrow_list, name='borrow_list'),
]