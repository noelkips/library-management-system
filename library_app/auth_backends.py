# library_app/auth_backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from library_app.models import Student  # adjust import if Student is in another app

UserModel = get_user_model()

class EmailOrCINBackend(ModelBackend):
    """
    Custom backend to authenticate using either email or student CIN (child_ID)
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        print(f"\n🔍 Attempting login for: {username}")
        user = None

        # Try finding by email
        try:
            user = UserModel.objects.get(email__iexact=username)
            print("✅ Found user by EMAIL")
        except UserModel.DoesNotExist:
            # Try to find by student CIN
            try:
                student = Student.objects.get(child_ID=username)
                user = student.user
                print("✅ Found user by STUDENT CIN")
            except Student.DoesNotExist:
                print("❌ No user found by email or CIN")
                return None

        # Now check password
        if user.check_password(password):
            print("✅ Password matched successfully!")
            return user
        else:
            print("❌ Password did not match!")
            return None
