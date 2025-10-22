from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from library_app.models import Student  # adjust import as needed

UserModel = get_user_model()

class EmailOrChildIDBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Try email first
        try:
            user = UserModel.objects.get(email=username)
        except UserModel.DoesNotExist:
            # If not email, try child_ID via Student model
            try:
                student = Student.objects.get(child_ID=username)
                user = student.user
            except Student.DoesNotExist:
                return None

        if user and user.check_password(password):
            return user
        return None

    def get_user(self, user_id):
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
