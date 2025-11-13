from .book_urls import book_urlpatterns
from .auth_urls import auth_urlpatterns
from .student_urls import student_urlpatterns
from .borrow_urls import borrow_urlpatterns
from .notification_urls import notification_urlpatterns
from .catalogue_urls import catalogue_urlpatterns


urlpatterns = book_urlpatterns + auth_urlpatterns + student_urlpatterns + borrow_urlpatterns + notification_urlpatterns + catalogue_urlpatterns


