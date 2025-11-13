from django.core.mail import send_mail
from django.conf import settings

def send_custom_email(subject, message, recipient_list):
    """
    A utility function to send a simple email.
    recipient_list should be a list of emails, e.g., ['user@example.com']
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        print(f"Email sent successfully to {recipient_list}")
        return True
    except Exception as e:
        # In a real app, you'd want to log this error
        print(f"Error sending email: {e}")
        return False