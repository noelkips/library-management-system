from .book_urls import book_urlpatterns
from .auth_urls import auth_urlpatterns

urlpatterns = book_urlpatterns + auth_urlpatterns