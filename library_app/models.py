from simple_history.models import HistoricalRecords
from django.contrib.auth.models import AbstractUser, PermissionsMixin, Group, Permission
from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from datetime import timedelta
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
import re



class Centre(models.Model):
    name = models.CharField(max_length=300)
    centre_code = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return f"{self.name} ({self.centre_code})"


class School(models.Model):
    name = models.CharField(max_length=300)
    school_code = models.CharField(max_length=30, unique=True)
    centre = models.ForeignKey(Centre, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.name} ({self.school_code})"


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    username = None
    email = models.EmailField(unique=True)

    is_librarian = models.BooleanField(default=False)
    is_student = models.BooleanField(default=False)
    is_site_admin = models.BooleanField(default=False)
    is_teacher = models.BooleanField(default=False)
    is_other = models.BooleanField(default=False)
    centre = models.ForeignKey(
        'Centre', on_delete=models.SET_NULL, null=True, blank=True)
    force_password_change = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    groups = models.ManyToManyField(
        Group,
        related_name='customuser_set',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )

    user_permissions = models.ManyToManyField(
        Permission,
        related_name='customuser_permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def __str__(self):
        return self.email or "Unnamed User"


class Category(models.Model):
    """Book categories for better organization"""
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


from django.db import models
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords

class Book(models.Model):
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=200)
    category = models.ForeignKey(
        'Category',
        on_delete=models.SET_NULL,
        null=True,
        related_name='books'
    )
    book_code = models.CharField(max_length=50, blank=True, null=True)
    isbn = models.CharField(max_length=50, unique=True)
    publisher = models.CharField(max_length=200)
    year_of_publication = models.PositiveIntegerField()
    available_copies = models.BooleanField(default=True, help_text="Indicates if the book is available (Yes/No).")
    centre = models.ForeignKey(
        'Centre', on_delete=models.SET_NULL, null=True, related_name='books')
    added_by = models.ForeignKey(
        'CustomUser', on_delete=models.SET_NULL, null=True, related_name='books_added')
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        if 'user' in kwargs:
            setattr(self, '_history_user', kwargs.pop('user'))
        super().save(*args, **kwargs)

    def update_available_copies(self):
        """Update available_copies based on issued borrows."""
        issued_copies = Borrow.objects.filter(
            book=self,
            status='issued'
        ).exists()
        self.available_copies = not issued_copies
        super().save()

    def is_available(self):
        """Check if book is available."""
        return self.available_copies

    def clean(self):
        if self.year_of_publication and (self.year_of_publication < 1500 or self.year_of_publication > 2025):
            raise ValidationError({'year_of_publication': 'Year must be between 1500 and 2025.'})
        if not self.isbn:
            raise ValidationError({'isbn': 'ISBN is required.'})
        if len(self.isbn) < 8 or len(self.isbn) > 18:
            raise ValidationError({'isbn': 'ISBN must be between 8 and 18 characters.'})

    def __str__(self):
        centre_name = self.centre.name if self.centre and self.centre.name else "No Centre"
        return f"{self.title} ({self.book_code}) - {centre_name}"

    class Meta:
        unique_together = ('book_code', 'centre')



        
class Student(models.Model):
    GRADE_CHOICES = [
        ('K', 'Kindergarten'),
        ('1', 'Grade 1'),
        ('2', 'Grade 2'),
        ('3', 'Grade 3'),
        ('4', 'Grade 4'),
        ('5', 'Grade 5'),
        ('6', 'Grade 6'),
        ('7', 'Grade 7'),
        ('8', 'Grade 8'),
        ('9', 'Grade 9'),
        ('10', 'Grade 10'),
        ('11', 'Grade 11'),
        ('12', 'Grade 12'),
    ]

    child_ID = models.IntegerField(unique=True, blank=True, null=True)
    name = models.CharField(max_length=500)
    centre = models.ForeignKey(
        'Centre', on_delete=models.SET_NULL, null=True, blank=True)
    school = models.ForeignKey(
        'School', on_delete=models.SET_NULL, null=True, blank=True)
    user = models.OneToOneField('CustomUser', on_delete=models.CASCADE, null=True, blank=True, related_name='student_profile')
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES, null=True, blank=True)

    def __str__(self):
        return self.name


def get_user_borrow_limit(user):
    """Get borrow limit based on user type"""
    if user.is_teacher:
        return None  # No limit
    elif user.is_student or user.is_other:
        return 1
    return 0  # Default: no borrowing


def can_user_borrow(user):
    """Check if user can borrow more books"""
    limit = get_user_borrow_limit(user)

    if limit is None:  # Teachers - no limit
        return True

    if limit == 0:  # Not a borrower
        return False

    active_borrows = Borrow.objects.filter(
        user=user,
        status='issued'
    ).count()

    return active_borrows < limit


class TeacherBookIssue(models.Model):
    STATUS_CHOICES = [
        ('issued', 'Issued to Student'),
        ('returned', 'Returned to Teacher'),
    ]

    parent_borrow = models.ForeignKey(
        'Borrow',
        on_delete=models.CASCADE,
        related_name='teacher_issues',
        help_text="The original library borrow to the teacher"
    )
    teacher = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='books_issued_to_students',
        limit_choices_to={'is_teacher': True}
    )
    student_name = models.CharField(
        max_length=500,
        help_text="Student name (doesn't have to be a system user)"
    )
    student_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Student ID or identifier"
    )
    book = models.ForeignKey(
        'Book',
        on_delete=models.CASCADE,
        related_name='teacher_issues'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='issued'
    )
    issue_date = models.DateTimeField(auto_now_add=True)
    expected_return_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When teacher expects student to return"
    )
    actual_return_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When student actually returned to teacher"
    )
    notes = models.TextField(blank=True, null=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        if 'user' in kwargs:
            setattr(self, '_history_user', kwargs.pop('user'))
        super().save(*args, **kwargs)

    def is_overdue(self):
        """Check if student's return is overdue"""
        if self.expected_return_date and self.status == 'issued':
            return timezone.now() > self.expected_return_date
        return False

    def __str__(self):
        return f"{self.teacher.get_full_name() or self.teacher.email} → {self.student_name}: {self.book.title}"

    class Meta:
        ordering = ['-issue_date']
        verbose_name = "Teacher Book Issue"
        verbose_name_plural = "Teacher Book Issues"


class Reservation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]

    book = models.ForeignKey(
        'Book',
        on_delete=models.CASCADE,
        related_name='reservations',
        help_text="The book being reserved."
    )
    user = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='reservations',
        help_text="The user who reserved the book."
    )
    centre = models.ForeignKey(
        'Centre',
        on_delete=models.SET_NULL,
        null=True,
        related_name='reservations'
    )
    reservation_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField(
        help_text="Date when reservation expires if not fulfilled"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    notified = models.BooleanField(
        default=False,
        help_text="Whether user has been notified of availability"
    )
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        if not self.expiry_date:
            self.expiry_date = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)
        if self.pk is None:  # New reservation
            if self.user.is_student and self.user.borrows.filter(status='issued').count() >= 1:
                raise ValueError("Students can only borrow one book at a time")
            if self.user.borrows.filter(status='issued').count() >= 2 and not (self.user.is_student or self.user.is_teacher):
                raise ValueError("General users can only borrow up to two books at a time")
            if self.book.is_available() and (self.user.is_librarian or self.user.is_site_admin):
                Borrow.objects.create(
                    book=self.book,
                    user=self.user,
                    centre=self.centre,
                    status='issued',
                    request_date=timezone.now(),
                    issue_date=timezone.now(),
                    due_date=timezone.now() + timedelta(days=3),
                    issued_by=self.user
                )
                self.status = 'fulfilled'
                self.save()

    def __str__(self):
        return f"{self.user.email} reserved {self.book.title} - {self.status}"

    class Meta:
        ordering = ['reservation_date']


class Borrow(models.Model):
    STATUS_CHOICES = [
        ('requested', 'Requested'),
        ('issued', 'Issued'),
        ('returned', 'Returned'),
    ]

    book = models.ForeignKey(
        'Book',
        on_delete=models.CASCADE,
        related_name='borrows',
        help_text="The book being borrowed."
    )
    user = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='borrows',
        help_text="The user who borrowed the book."
    )
    centre = models.ForeignKey(
        'Centre',
        on_delete=models.SET_NULL,
        null=True,
        related_name='borrows'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='requested'
    )
    request_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the borrow was requested"
    )
    issue_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the book was actually issued by librarian"
    )
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The date by which the book must be returned."
    )
    return_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The date when the book was returned."
    )
    renewals = models.PositiveIntegerField(
        default=0,
        help_text="The number of times the borrow has been renewed."
    )
    issued_by = models.ForeignKey(
        'CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issued_borrows',
        help_text="The librarian who issued the book."
    )
    returned_to = models.ForeignKey(
        'CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_returns',
        help_text="The librarian who received the return."
    )
    notes = models.TextField(blank=True, null=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        if 'user' in kwargs:
            setattr(self, '_history_user', kwargs.pop('user'))
        super().save(*args, **kwargs)

    def is_overdue(self):
        """Check if borrow is overdue"""
        if self.due_date and self.status == 'issued':
            return timezone.now() > self.due_date
        return False

    def is_returned(self):
        """Check if book has been returned"""
        return self.status == 'returned'

    def renew(self, user, days=3):
        """Renew the borrow period"""
        if self.renewals < 2:  # Max 2 renewals
            self.renewals += 1
            self.due_date += timedelta(days=days)
            self.save(user=user)
            Notification.objects.create(
                user=self.user,
                message=f"'{self.book.title}' renewed. New due date: {self.due_date.strftime('%Y-%m-%d')}"
            )
            return True
        return False

    def __str__(self):
        return f"{self.user.email} - {self.book.title} ({self.status})"

    class Meta:
        ordering = ['-request_date']


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('borrow_request', 'Borrow Request'),
        ('borrow_approved', 'Borrow Approved'),
        ('borrow_rejected', 'Borrow Rejected'),
        ('book_issued', 'Book Issued'),
        ('book_returned', 'Book Returned'),
        ('book_available', 'Book Available'),
        ('reservation_fulfilled', 'Reservation Fulfilled'),
        ('teacher_bulk_request', 'Teacher Bulk Request'),
        ('overdue_reminder', 'Overdue Reminder'),
    ]

    user = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        default='borrow_request'
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    book = models.ForeignKey(
        'Book',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    borrow = models.ForeignKey(
        'Borrow',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    reservation = models.ForeignKey(
        'Reservation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    group_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Group ID for batched notifications"
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email}: {self.message[:50]}"

    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.save()

    def get_icon(self):
        """Get icon class based on notification type"""
        icons = {
            'borrow_request': 'book-open',
            'borrow_approved': 'check-circle',
            'borrow_rejected': 'x-circle',
            'book_issued': 'gift',
            'book_returned': 'undo',
            'book_available': 'bell',
            'reservation_fulfilled': 'star',
            'teacher_bulk_request': 'books',
            'overdue_reminder': 'alert-circle',
        }
        return icons.get(self.notification_type, 'bell')

    def get_color(self):
        """Get color class based on notification type"""
        colors = {
            'borrow_request': 'blue',
            'borrow_approved': 'green',
            'borrow_rejected': 'red',
            'book_issued': 'purple',
            'book_returned': 'teal',
            'book_available': 'amber',
            'reservation_fulfilled': 'pink',
            'teacher_bulk_request': 'indigo',
            'overdue_reminder': 'orange',
        }
        return colors.get(self.notification_type, 'gray')


@receiver(post_save, sender=CustomUser)
def create_student_profile(sender, instance, created, **kwargs):
    if created and instance.is_student and not hasattr(instance, 'student_profile'):
        school = None
        if hasattr(instance, '_school_id') and instance._school_id:
            try:
                school = School.objects.get(id=instance._school_id)
            except School.DoesNotExist:
                school = None
            del instance._school_id

        child_ID = getattr(instance, '_child_ID', None)
        if hasattr(instance, '_child_ID'):
            del instance._child_ID

        if not instance.email:
            instance.email = f"student{child_ID}@libraryhub.com" if child_ID else f"student{instance.id}@libraryhub.com"
            instance.save(update_fields=["email"])

        Student.objects.create(
            user=instance,
            name=f"{instance.first_name} {instance.last_name}".strip(),
            centre=instance.centre,
            child_ID=child_ID,
            school=school,
        )


@receiver(post_save, sender=Borrow)
def update_book_availability(sender, instance, **kwargs):
    """Update book's available_copies field when a borrow record is created or updated."""
    instance.book.update_available_copies()


@receiver(post_delete, sender=Borrow)
def update_book_availability_on_delete(sender, instance, **kwargs):
    """Update book's available_copies field when a borrow record is deleted."""
    instance.book.update_available_copies()


class Catalogue(models.Model):
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='catalogue_entries',
        help_text="The book being catalogued."
    )
    shelf_number = models.CharField(
        max_length=50,
        help_text="The shelf location (e.g., 'A1', 'B2-3', 'Reference-1')"
    )
    centre = models.ForeignKey(
        Centre,
        on_delete=models.SET_NULL,
        null=True,
        related_name='catalogues',
        help_text="The centre where the book is shelved."
    )
    added_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='catalogues_added',
        help_text="The user who added this catalogue entry."
    )
    added_date = models.DateTimeField(
        auto_now_add=True,
        help_text="The date when the catalogue entry was created."
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="The date when the catalogue entry was last updated."
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes about the book's location or condition."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this catalogue entry is currently active."
    )
    history = HistoricalRecords()

    class Meta:
        unique_together = ('book', 'centre')
        ordering = ['shelf_number']
        verbose_name_plural = 'Catalogues'

    def save(self, *args, **kwargs):
        if 'user' in kwargs:
            setattr(self, '_history_user', kwargs.pop('user'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.book.title} - Shelf {self.shelf_number}"