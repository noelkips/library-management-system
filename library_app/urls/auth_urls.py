from django.urls import path
from .. import views


auth_urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('login/', views.login_view, name='login_view'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    path('manage-users/', views.manage_users, name='manage_users'),
    path('users/add', views.user_add, name='user_add'),
    path('users/<int:pk>/delete', views.user_delete, name='user_delete'),
    path('users/<int:pk>/update', views.user_update, name='user_update'),
    path('users/<int:pk>/reset_password', views.user_reset_password, name='user_reset_password'),
     path('get-schools-by-centre/', views.get_schools_by_centre, name='get_schools_by_centre'),
    
]


