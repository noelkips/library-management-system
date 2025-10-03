
from simple_history.models import HistoricalRecords
from django.contrib.auth.models import AbstractUser, PermissionsMixin, Group, Permission
from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.contrib.auth.models import BaseUserManager
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
    is_available = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if 'user' in kwargs:
            setattr(self, '_history_user', kwargs.pop('user'))
        if self.available_copies > self.total_copies:
            self.available_copies = self.total_copies
        super().save(*args, **kwargs)
        # if self.pk is None:  # New book
        #     admins = CustomUser.objects.filter(is_superuser=True)
        #     for admin in admins:
        #         Notification.objects.create(
        #             user=admin,
        #             message=f"New book '{self.title}' added by {self.added_by.first_name if self.added_by else 'Unknown'} at {self.centre.name}.",
        #             content_type=ContentType.objects.get_for_model(self),
        #             object_id=self.id
        #         )

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
    

# Issue Model
class Issue(models.Model):
    book = models.ForeignKey(
        'Book', 
        on_delete=models.CASCADE, 
        related_name='issues',
        help_text="The book being issued."
    )
    user = models.ForeignKey(
        'Student', 
        on_delete=models.CASCADE, 
        related_name='issues',
        help_text="The student to whom the book is issued."
    )
    centre = models.ForeignKey(
        'Centre', 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='issues',
        help_text="The centre where the book is issued."
    )
    issued_by = models.ForeignKey(
        'CustomUser', 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='books_issued',
        help_text="The user (librarian or admin) who issued the book."
    )
    issue_date = models.DateTimeField(
        auto_now_add=True,
        help_text="The date and time when the book was issued."
    )
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        if 'user' in kwargs:
            setattr(self, '_history_user', kwargs.pop('user'))
        super().save(*args, **kwargs)
        if self.pk is None:  # New issue
            if not self.issued_by.is_librarian and not self.issued_by.is_site_admin:
                raise ValueError("Only librarians or site admins can issue books")
            if self.user.user.is_student and self.user.user.borrows.filter(is_returned=False).count() >= 1:
                raise ValueError("Students can only borrow one book at a time")
            if self.user.user.borrows.filter(is_returned=False).count() >= 2 and not (self.user.user.is_student or self.user.user.is_teacher):
                raise ValueError("General users can only borrow up to two books at a time")
            if self.book.available_copies < 1:
                raise ValueError("No available copies of this book")
            # Create a Borrow record
            Borrow.objects.create(
                book=self.book,
                user=self.user.user,  # Use the related CustomUser for Borrow
                centre=self.centre,
                issued_by=self.issued_by,
                due_date=timezone.now() + timedelta(days=3)
            )
            Notification.objects.create(
                user=self.user.user,  # Notify the related CustomUser
                message=f"Book '{self.book.title}' issued to you by {self.issued_by.email} at {self.centre.name}.",
                content_type=ContentType.objects.get_for_model(self),
                object_id=self.id
            )

    def __str__(self):
        return f"{self.book.title} issued to {self.user.name} by {self.issued_by.email if self.issued_by else 'Unknown'}"

# Borrow Model
class Borrow(models.Model):
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
        related_name='borrows',
        help_text="The centre where the book was borrowed."
    )
    borrow_date = models.DateTimeField(
        auto_now_add=True,
        help_text="The date and time when the book was borrowed."
    )
    due_date = models.DateTimeField(
        help_text="The date by which the book must be returned."
    )
    return_date = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="The date when the book was returned, if applicable."
    )
    renewals = models.PositiveIntegerField(
        default=0,
        help_text="The number of times the borrow has been renewed."
    )
    is_returned = models.BooleanField(
        default=False,
        help_text="Indicates whether the book has been returned."
    )
    issued_by = models.ForeignKey(
        'CustomUser', 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='issued_borrows',
        help_text="The user who issued the book."
    )
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        if 'user' in kwargs:
            setattr(self, '_history_user', kwargs.pop('user'))
        is_new = not self.pk  # Check if this is a new borrow
        from_issue_view = kwargs.pop('from_issue_view', False)  # Optional parameter
        super().save(*args, **kwargs)

        if is_new and not from_issue_view:  # Only decrement if not from issue_view
            self.book.available_copies -= 1
            self.book.save()
            Notification.objects.create(
                user=self.user,
                message=f"You borrowed '{self.book.title}'. Due: {self.due_date.strftime('%Y-%m-%d')}",
                content_type=ContentType.objects.get_for_model(self),
                object_id=self.id
            )
        elif self.is_returned and not self.return_date:  # Return processed
            self.return_date = timezone.now()
            self.book.available_copies += 1
            self.book.save()
            Notification.objects.create(
                user=self.user,
                message=f"You returned '{self.book.title}' on {self.return_date.strftime('%Y-%m-%d')}",
                content_type=ContentType.objects.get_for_model(self),
                object_id=self.id
            )

    def renew(self, user):
        if self.renewals < 2:  # Max 2 renewals
            self.renewals += 1
            self.due_date += timedelta(days=3)
            self.save(user=user)
            Notification.objects.create(
                user=self.user,
                message=f"'{self.book.title}' renewed. New due date: {self.due_date.strftime('%Y-%m-%d')}",
                content_type=ContentType.objects.get_for_model(self),
                object_id=self.id
            )
        else:
            raise ValueError("Maximum renewals reached")

    def __str__(self):
        return f"{self.user.email} borrowed {self.book.title}"

# Notification Model
class Notification(models.Model):
    user = models.ForeignKey(
        'CustomUser', 
        on_delete=models.CASCADE, 
        related_name='notifications',
        help_text="The user who receives the notification."
    )
    message = models.TextField(
        help_text="The content of the notification."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="The date and time when the notification was created."
    )
    is_read = models.BooleanField(
        default=False,
        help_text="Indicates whether the notification has been read."
    )
    responded_by = models.ForeignKey(
        'CustomUser', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='responded_notifications',
        help_text="The user who responded to the notification, if applicable."
    )
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="The type of object related to the notification."
    )
    object_id = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="The ID of the related object."
    )
    related_object = GenericForeignKey('content_type', 'object_id')
    history = HistoricalRecords()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.email}: {self.message}"
    
   


@receiver(post_save, sender=CustomUser)
def create_student_profile(sender, instance, created, **kwargs):
    """
    Automatically create a Student profile whenever a CustomUser with is_student=True is created.
    - If child_ID and school info were passed via temporary attributes (_child_ID, _school_id), use them.
    - If email is missing, generate a default student email.
    """
    if created and instance.is_student and not hasattr(instance, 'student_profile'):
        # Handle school from temporary attribute
        school = None
        if hasattr(instance, '_school_id') and instance._school_id:
            try:
                school = School.objects.get(id=instance._school_id)
            except School.DoesNotExist:
                school = None
            del instance._school_id  # clean up

        # Handle child_ID from temporary attribute
        child_ID = getattr(instance, '_child_ID', None)
        if hasattr(instance, '_child_ID'):
            del instance._child_ID  # clean up

        # If email is empty, generate one (autogenerated format)
        if not instance.email:
            instance.email = f"student{child_ID}@libraryhub.com" if child_ID else f"student{instance.id}@libraryhub.com"
            instance.save(update_fields=["email"])

        # Create Student profile linked to this user
        Student.objects.create(
            user=instance,
            name=f"{instance.first_name} {instance.last_name}".strip(),
            centre=instance.centre,
            child_ID=child_ID,
            school=school,
        )



