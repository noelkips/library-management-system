from .book_urls import book_urlpatterns
from .auth_urls import auth_urlpatterns
from .student_urls import student_urlpatterns
# from .issue_urls import issue_urlpatterns
# from .borrow_urls import borrow_urlpatterns

urlpatterns = book_urlpatterns + auth_urlpatterns + student_urlpatterns 