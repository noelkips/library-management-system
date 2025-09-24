# library_app/urls/books_urls.py
from django.urls import path
from library_app import views  # Fully qualified import

urlpatterns = [
    path('', views.about, name='books_index'),
]
