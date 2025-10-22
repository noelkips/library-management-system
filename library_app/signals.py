"""
Signal handlers for automatic notification creation
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from .models import Borrow, Reservation, Notification, CustomUser, TeacherBookIssue
import hashlib


@receiver(post_save, sender=Borrow)
def handle_borrow_notification(sender, instance, created, **kwargs):
    """
    Create notifications when borrow status changes.
    - When issued: notify the borrower that their request was approved
    - When returned: notify the borrower with thank you message
    """
    if not created and instance.status == 'issued':
        Notification.objects.create(
            user=instance.user,
            notification_type='book_issued',
            message=(
                f"Your request for '{instance.book.title}' has been approved! "
                f"Due date: {instance.due_date.strftime('%Y-%m-%d')}"
            ),
            book=instance.book,
            borrow=instance,
        )
    elif not created and instance.status == 'returned':
        Notification.objects.create(
            user=instance.user,
            notification_type='book_returned',
            message=f"Thank you for returning '{instance.book.title}'!",
            book=instance.book,
            borrow=instance,
        )


@receiver(post_save, sender=Reservation)
def handle_reservation_notification(sender, instance, created, **kwargs):
    """
    Create notifications for reservations.
    - When created: notify librarians about the reservation
    - When book available: notify both user and librarians
    """
    if created:
        librarians = CustomUser.objects.filter(
            is_librarian=True,
            centre=instance.centre
        )
        for librarian in librarians:
            Notification.objects.create(
                user=librarian,
                notification_type='borrow_request',
                message=(
                    f"{instance.user.get_full_name() or instance.user.email} "
                    f"reserved '{instance.book.title}'"
                ),
                book=instance.book,
                reservation=instance,
            )
    elif instance.notified and instance.status == 'pending':
        # Notify the user with reservation
        Notification.objects.create(
            user=instance.user,
            notification_type='book_available',
            message=(
                f"'{instance.book.title}' is now available! "
                f"Your reservation is ready. Please request to borrow within 2 days."
            ),
            book=instance.book,
            reservation=instance,
        )
        
        # Notify librarians
        librarians = CustomUser.objects.filter(
            is_librarian=True,
            centre=instance.centre
        )
        for librarian in librarians:
            Notification.objects.create(
                user=librarian,
                notification_type='reservation_fulfilled',
                message=(
                    f"'{instance.book.title}' is available for "
                    f"{instance.user.get_full_name() or instance.user.email}'s reservation"
                ),
                book=instance.book,
                reservation=instance,
            )


def create_teacher_bulk_notification(librarian, teacher, books_list, centre):
    """
    Create a single grouped notification for teacher bulk requests
    instead of multiple individual notifications. This batches all books
    requested by a teacher into one notification per librarian per day.
    """
    group_id = hashlib.md5(
        f"{teacher.id}-{timezone.now().date()}".encode()
    ).hexdigest()
    
    book_titles = ", ".join([f"'{b.title}'" for b in books_list[:3]])
    if len(books_list) > 3:
        book_titles += f", and {len(books_list) - 3} more"
    
    message = (
        f"{teacher.get_full_name() or teacher.email} requested "
        f"{len(books_list)} book{'s' if len(books_list) != 1 else ''}: {book_titles}"
    )
    
    Notification.objects.create(
        user=librarian,
        notification_type='teacher_bulk_request',
        message=message,
        group_id=group_id,
    )


def notify_librarians_of_borrow_request(borrow):
    """
    Notify librarians when a student/teacher makes a borrow request.
    This is called from the borrow_request view for single requests.
    """
    librarians = CustomUser.objects.filter(
        is_librarian=True,
        centre=borrow.centre
    )
    for librarian in librarians:
        Notification.objects.create(
            user=librarian,
            notification_type='borrow_request',
            message=(
                f"{borrow.user.get_full_name() or borrow.user.email} "
                f"requested to borrow '{borrow.book.title}'"
            ),
            book=borrow.book,
            borrow=borrow,
        )
