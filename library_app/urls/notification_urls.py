from django.urls import path
from .. import views
# app_name = 'students'

notification_urlpatterns = [
    path('notifications/', views.notification_center, name='notification_center'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/<int:notification_id>/delete/', views.delete_notification, name='delete_notification'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('notifications/clear-all/', views.clear_all_notifications, name='clear_all_notifications'),
    path('api/notifications/unread-count/', views.get_unread_count, name='get_unread_count'),
    path('api/notifications/recent/', views.get_recent_notifications, name='get_recent_notifications'),
]

  

