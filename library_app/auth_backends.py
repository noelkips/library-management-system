from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from library_app.models import Student

UserModel = get_user_model()

class EmailOrChildIDBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username:
            return None
            
        # Try email first
        try:
            user = UserModel.objects.get(email=username)
        except UserModel.DoesNotExist:
            # If not found by email, check if username looks like a child_ID (numeric)
            # Only attempt child_ID lookup if the username is numeric
            if username.isdigit():
                try:
                    child_id = int(username)
                    student = Student.objects.get(child_ID=child_id)
                    user = student.user
                except (Student.DoesNotExist, ValueError):
                    return None
            else:
                # Username is not numeric and not a valid email
                return None

        # Verify password
        if user and user.check_password(password):
            return user
        return None

    def get_user(self, user_id):
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None