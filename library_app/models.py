from simple_history.models import HistoricalRecords
from django.contrib.auth.models import AbstractUser, PermissionsMixin, Group, Permission
from django.contrib.auth.base_user import BaseUserManager
from django.db import models, transaction
from django.db.models import F
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from datetime import timedelta
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
import re
from datetime import datetime

from django.db import models
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords
import re
from datetime import datetime
from django.db import transaction
from django.db import models
from django.core.exceptions import ValidationError

# library_app/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords
from django.utils import timezone
from datetime import timedelta
import re
from django.db import transaction
from django.dispatch import receiver
from django.db.models.signals import post_save


class Centre(models.Model):
    name = models.CharField(max_length=300)
    centre_code = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Library Centre"
        verbose_name_plural = "Library Centres"


class Grade(models.Model):
    name = models.CharField(max_length=100, unique=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = "Grades"

    def __str__(self):
        return self.name


class School(models.Model):
    name = models.CharField(max_length=300)
    centre = models.ForeignKey(Centre, on_delete=models.CASCADE, related_name='schools')
    active_grades = models.ManyToManyField(Grade, related_name='schools', blank=True)

    def __str__(self):
        return f"{self.name} ({self.centre.name})"


class Category(models.Model):
    name = models.CharField(max_length=200, unique=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Subject(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subjects')
    grade = models.ForeignKey(
    Grade,
    on_delete=models.CASCADE,
    related_name='subjects',
    null=True,
    blank=True,
    help_text="Required only for Textbook subjects"
)
    class Meta:
        unique_together = ('name', 'grade', 'category')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.grade} - {self.category})"


# Optional: For auto-generating book_id sequences per centre+subject
class BookIDSequence(models.Model):
    centre = models.ForeignKey(Centre, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('centre', 'subject')

    def __str__(self):
        return f"{self.centre} - {self.subject or 'General'} #{self.last_number}"

class CustomUserManager(BaseUserManager):
    def create_user(self, login_id, password=None, **extra_fields):
        if not login_id:
            raise ValueError("Login ID is required")

        # Only normalize email for non-students
        if not extra_fields.get('is_student', False):
            login_id = self.normalize_email(login_id)

        user = self.model(login_id=login_id, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, login_id, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_site_admin', True)

        if not login_id:
            raise ValueError("Superuser must have a login ID")

        return self.create_user(login_id, password, **extra_fields)


# models.py

class CustomUser(AbstractUser):
    username = None

    login_id = models.CharField(
        max_length=254,
        unique=True,
        db_index=True,
        help_text="Child ID for students, email for staff/librarians"
    )
    email = models.EmailField(blank=True, null=True, unique=False)

    is_librarian = models.BooleanField(default=False)
    is_student = models.BooleanField(default=False)
    is_teacher = models.BooleanField(default=False)
    is_site_admin = models.BooleanField(default=False)
    is_other = models.BooleanField(default=True, help_text="Regular staff (accountant, guard, etc.)")  # ← NEW

    centre = models.ForeignKey(Centre, on_delete=models.SET_NULL, null=True, blank=True)
    force_password_change = models.BooleanField(default=False)

    USERNAME_FIELD = 'login_id'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def clean(self):
        if not self.is_student and self.login_id and '@' not in self.login_id:
            raise ValidationError("Staff must use a valid email as login ID")

    def save(self, *args, **kwargs):
        # Auto-sync email
        if not self.is_student and self.login_id:
            self.email = self.login_id

        # === AUTOMATIC ROLE LOGIC ===
        if self.is_student:
            # Students have no staff roles
            self.is_librarian = False
            self.is_teacher = False
            self.is_site_admin = False
            self.is_other = False
        else:
            # Staff: if any special role → is_other = False
            # if no special role → is_other = True
            has_special_role = (
                self.is_librarian or
                self.is_teacher or
                self.is_site_admin
            )
            self.is_other = not has_special_role

        super().save(*args, **kwargs)

    def __str__(self):
        if self.is_student and hasattr(self, 'student_profile'):
            return f"Student {self.student_profile.child_ID} - {self.student_profile.name}"
        return self.login_id

# MAIN BOOK MODEL — FINAL WORKING VERSION
class Book(models.Model):
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=200)
    isbn = models.CharField(max_length=50, blank=True)
    publisher = models.CharField(max_length=200, blank=True)
    year_of_publication = models.PositiveIntegerField()

    # LOCATION
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='books')
    centre = models.ForeignKey(Centre, on_delete=models.CASCADE, related_name='books', null=True, blank=True)

    # CONTENT — Subject is OPTIONAL for Fiction, Reference, etc.
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name='books',
        null=True,
        blank=True  # ← CRITICAL: Allows non-textbook books
    )

    book_id = models.CharField(max_length=100, unique=True, blank=True)
    book_code = models.CharField(max_length=50, blank=True, null=True)
    added_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='added_books')
    available_copies = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['title']
        indexes = [
            models.Index(fields=['centre']),
            models.Index(fields=['subject']),
            models.Index(fields=['school']),
        ]

    def clean(self):
        # Auto-set centre from school
        if self.school:
            self.centre = self.school.centre

        # ONLY validate grade/school compatibility if:
        # - There is a subject
        # - AND the subject's category is Textbook
        if self.subject and hasattr(self.subject, 'category'):
            if self.subject.category.name.lower() == 'textbook':
                if not self.subject.grade:
                    raise ValidationError("Textbook must have a Grade")

                if self.school and self.subject.grade not in self.school.active_grades.all():
                    raise ValidationError(
                        f"School '{self.school}' does not offer {self.subject.grade}"
                    )

        # ISBN validation
        if self.isbn and not (4 <= len(self.isbn.strip()) <= 20):
            raise ValidationError("ISBN must be 4–20 characters")

    def save(self, *args, **kwargs):
        self.full_clean()

        if self.school and not self.centre:
            self.centre = self.school.centre

        # ONLY generate book_id when creating a new book (not on update)
        if not self.pk and not self.book_id and self.centre:
            with transaction.atomic():
                seq, _ = BookIDSequence.objects.select_for_update().get_or_create(
                    centre=self.centre,
                    subject=self.subject,
                    defaults={'last_number': 0}
                )
                seq.last_number += 1
                seq.save()

                c_prefix = re.sub(r'[^A-Z0-9]', '', self.centre.name.upper())[:4].ljust(4, 'X')
                s_prefix = re.sub(r'[^A-Z0-9]', '', (self.subject.name if self.subject else "GEN").upper())[:4].ljust(4, 'X')
                self.book_id = f"{c_prefix}/{s_prefix}/{seq.last_number:04d}/{timezone.now().year}"

        super().save(*args, **kwargs)

    @property
    def category(self):
        return self.subject.category if self.subject else None

    @property
    def grade(self):
        return self.subject.grade if self.subject else None

    @property
    def category_name(self):
        return self.category.name if self.category else "General"

    @property
    def grade_name(self):
        return self.grade.name if self.grade else "All Grades"

    def __str__(self):
        return f"{self.title} | {self.category_name} | {self.grade_name} | {self.school}"

class Student(models.Model):
    GRADE_CHOICES = [
        ('K', 'Kindergarten'), ('1', 'Grade 1'), ('2', 'Grade 2'), ('3', 'Grade 3'),
        ('4', 'Grade 4'), ('5', 'Grade 5'), ('6', 'Grade 6'), ('7', 'Grade 7'),
        ('8', 'Grade 8'), ('9', 'Grade 9'), ('10', 'Grade 10'), ('11', 'Grade 11'), ('12', 'Grade 12'),
    ]

    child_ID = models.CharField(          # ← Changed from IntegerField to CharField
        max_length=50,
        unique=True,
        db_index=True,
        help_text="This is the student's login ID"
    )
    name = models.CharField(max_length=500)
    centre = models.ForeignKey('Centre', on_delete=models.SET_NULL, null=True, blank=True)
    school = models.ForeignKey('School', on_delete=models.SET_NULL, null=True, blank=True)
    user = models.OneToOneField('CustomUser', on_delete=models.CASCADE, null=True, blank=True, related_name='student_profile')
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES, null=True, blank=True)

    def __str__(self):
        return f"{self.name} (ID: {self.child_ID})"

    # In your Student model (add this)
    def save(self, *args, **kwargs):
        old_child_id = None
        if self.pk:
            old_child_id = Student.objects.get(pk=self.pk).child_ID

        super().save(*args, **kwargs)

        # If child_ID changed and user exists → update login_id
        if self.user and old_child_id and old_child_id != self.child_ID:
            self.user.login_id = self.child_ID
            self.user.save(update_fields=['login_id'])
            
            # Optional: reset password to new child_ID
            self.user.set_password(self.child_ID)
            self.user.force_password_change = True
            self.user.save()


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


@receiver(post_save, sender=Student)
def create_student_user(sender, instance, created, **kwargs):
    if not instance.user:
        user = CustomUser.objects.create_user(
            login_id=instance.child_ID,
            password=None,
            is_student=True,
            first_name=instance.name.split(maxsplit=1)[0] if instance.name else '',
            last_name=instance.name.split(maxsplit=1)[1] if ' ' in instance.name else '',
            centre=instance.centre,
        )
        user.set_unusable_password()
        instance.user = user
        instance.save(update_fields=['user'])



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