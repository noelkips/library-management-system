from django.urls import path
from ..views import catalogue_add, catalogue_list, catalogue_update, catalogue_delete, get_books_by_centre

catalogue_urlpatterns = [
    path('catalogue/add/', catalogue_add, name='catalogue_add'),
    path('catalogue/list/', catalogue_list, name='catalogue_list'),
    path('catalogue/update/<int:pk>/', catalogue_update, name='catalogue_update'),
    path('catalogue/delete/<int:pk>/', catalogue_delete, name='catalogue_delete'),
    path('catalogue/api/books-by-centre/', get_books_by_centre, name='get_books_by_centre'),
]
