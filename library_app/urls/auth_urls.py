from django.urls import path
from .. import views

# app_name = 'books'

auth_urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('login/', views.login_view, name='login_view'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    path('manage-users/', views.manage_users, name='manage_users'),
    
]


