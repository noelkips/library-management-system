from simple_history.models import HistoricalRecords
from django.contrib.auth.models import AbstractUser, PermissionsMixin, Group, Permission
from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver


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

    objects = CustomUserManager()  # Assign the custom manager here

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


class Book(models.Model):
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    book_code = models.CharField(max_length=50, unique=True)
    publisher = models.CharField(max_length=200)
    year_of_publication = models.PositiveIntegerField()
    total_copies = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)
    centre = models.ForeignKey(
        'Centre', on_delete=models.SET_NULL, null=True, related_name='books')
    added_by = models.ForeignKey(
        'CustomUser', on_delete=models.SET_NULL, null=True, related_name='books_added')
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        if 'user' in kwargs:
            setattr(self, '_history_user', kwargs.pop('user'))
        if self.available_copies > self.total_copies:
            self.available_copies = self.total_copies
        super().save(*args, **kwargs)

    def is_available(self):
        """Check if book has available copies"""
        return self.available_copies > 0

    def __str__(self):
        centre_name = self.centre.name if self.centre and self.centre.name else "No Centre"
        return f"{self.title} ({self.book_code}) - {centre_name}"

    class Meta:
        unique_together = ('book_code', 'centre')


class Student(models.Model):
    child_ID = models.IntegerField(unique=True, blank=True, null=True)
    name = models.CharField(max_length=500)
    centre = models.ForeignKey(
        'Centre', on_delete=models.SET_NULL, null=True, blank=True)
    school = models.CharField(max_length=500)
    user = models.OneToOneField('CustomUser', on_delete=models.CASCADE, null=True, blank=True, related_name='student_profile')
    
    def __str__(self):
        return self.name
    
    def can_borrow(self):
        """Check if student can borrow more books"""
        active_borrows = Borrow.objects.filter(
            user=self.user, 
            is_returned=False
        ).count()
        return active_borrows < 1  # Students can only have 1 book at a time


# <CHANGE> New Reservation model for when books are unavailable
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

    def __str__(self):
        return f"{self.user.email} reserved {self.book.title} - {self.status}"

    class Meta:
        ordering = ['reservation_date']


# <CHANGE> Updated Borrow model with clearer workflow
class Borrow(models.Model):
    STATUS_CHOICES = [
        ('requested', 'Requested'),  # Student requested to borrow
        ('issued', 'Issued'),  # Librarian issued the book
        ('returned', 'Returned'),  # Book has been returned
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


# Remove the old Issue model as it's now integrated into Borrow


class Notification(models.Model):
    user = models.ForeignKey(
        'CustomUser', 
        on_delete=models.CASCADE, 
        related_name='notifications'
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    responded_by = models.ForeignKey(
        'CustomUser', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='responded_notifications'
    )
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey('content_type', 'object_id')
    history = HistoricalRecords()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.email}: {self.message}"


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


