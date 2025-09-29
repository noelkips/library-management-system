
from simple_history.models import HistoricalRecords
from django.contrib.auth.models import AbstractUser, PermissionsMixin, Group, Permission
from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.contrib.auth.models import BaseUserManager

class Centre(models.Model):
    name = models.CharField(max_length=300)
    centre_code = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return f"{self.name} ({self.centre_code})"


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
    is_teacher = models.BooleanField(default=False)
    centre = models.ForeignKey(
        'Centre', on_delete=models.SET_NULL, null=True, blank=True)

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
    CIN = models.IntegerField(unique=True, blank=True, null=True)
    name = models.CharField(max_length=500)
    centre = models.ForeignKey(
        'Centre', on_delete=models.SET_NULL, null=True, blank=True)
    school = models.CharField(max_length=500)

    def __str__(self):
        return self.name


# class Issue(models.Model):
#     book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='issues')
#     user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='issues')
#     centre = models.ForeignKey('Centre', on_delete=models.SET_NULL, null=True, related_name='issues')
#     issued_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='books_issued')
#     issue_date = models.DateTimeField(auto_now_add=True)
#     history = HistoricalRecords()
#
#     def save(self, *args, **kwargs):
#         if 'user' in kwargs:
#             self._history_user = kwargs.pop('user')
#         super().save(*args, **kwargs)
#         if self.pk is None:  # New issue
#             if not self.issued_by.is_librarian and not self.issued_by.is_superuser:
#                 raise ValueError("Only librarians or admins can issue books")
#             if self.user.is_student and self.user.borrows.filter(is_returned=False).count() >= 1:
#                 raise ValueError("Students can only borrow one book at a time")
#             if self.user.borrows.filter(is_returned=False).count() >= 2 and not (self.user.is_student or self.user.is_teacher):
#                 raise ValueError("General users can only borrow up to two books at a time")
#             if self.book.available_copies < 1:
#                 raise ValueError("No available copies of this book")
#             # Create a Borrow record
#             Borrow.objects.create(
#                 book=self.book,
#                 user=self.user,
#                 centre=self.centre,
#                 issued_by=self.issued_by,
#                 due_date=timezone.now() + timedelta(days=3)
#             )
#             Notification.objects.create(
#                 user=self.user,
#                 message=f"Book '{self.book.title}' issued to you by {self.issued_by.username} at {self.centre.name}.",
#                 content_type=ContentType.objects.get_for_model(self),
#                 object_id=self.id
#             )
#
#     def __str__(self):
#         return f"{self.book.title} issued to {self.user.username} by {self.issued_by.username}"
#
# class Borrow(models.Model):
#     book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='borrows')
#     user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='borrows')
#     centre = models.ForeignKey('Centre', on_delete=models.SET_NULL, null=True, related_name='borrows')
#     borrow_date = models.DateTimeField(auto_now_add=True)
#     due_date = models.DateTimeField()
#     return_date = models.DateTimeField(null=True, blank=True)
#     renewals = models.PositiveIntegerField(default=0)
#     is_returned = models.BooleanField(default=False)
#     issued_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='issued_borrows')
#     history = HistoricalRecords()
#
#     def save(self, *args, **kwargs):
#         if 'user' in kwargs:
#             self._history_user = kwargs.pop('user')
#         if not self.pk:  # New borrow
#             self.book.available_copies -= 1
#             self.book.save()
#             Notification.objects.create(
#                 user=self.user,
#                 message=f"You borrowed '{self.book.title}'. Due: {self.due_date.strftime('%Y-%m-%d')}",
#                 content_type=ContentType.objects.get_for_model(self),
#                 object_id=self.id
#             )
#         elif self.is_returned and not self.return_date:  # Return processed
#             self.return_date = timezone.now()
#             self.book.available_copies += 1
#             self.book.save()
#             Notification.objects.create(
#                 user=self.user,
#                 message=f"You returned '{self.book.title}' on {self.return_date.strftime('%Y-%m-%d')}",
#                 content_type=ContentType.objects.get_for_model(self),
#                 object_id=self.id
#             )
#             # Notify users with active reservations
#             reservations = Reservation.objects.filter(book=self.book, is_active=True)
#             for reservation in reservations:
#                 Notification.objects.create(
#                     user=reservation.user,
#                     message=f"Reserved book '{self.book.title}' is now available at {self.centre.name}.",
#                     content_type=ContentType.objects.get_for_model(reservation),
#                     object_id=reservation.id
#                 )
#         super().save(*args, **kwargs)
#
#     def renew(self, user):
#         if self.renewals < 2:  # Max 2 renewals
#             self.renewals += 1
#             self.due_date += timedelta(days=3)
#             self.save(user=user)
#             Notification.objects.create(
#                 user=self.user,
#                 message=f"'{self.book.title}' renewed. New due date: {self.due_date.strftime('%Y-%m-%d')}",
#                 content_type=ContentType.objects.get_for_model(self),
#                 object_id=self.id
#             )
#         else:
#             raise ValueError("Maximum renewals reached")
#
#     def __str__(self):
#         return f"{self.user.username} borrowed {self.book.title}"
#
# class Reservation(models.Model):
#     book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='reservations')
#     user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='reservations')
#     centre = models.ForeignKey('Centre', on_delete=models.SET_NULL, null=True, related_name='reservations')
#     reservation_date = models.DateTimeField(auto_now_add=True)
#     is_active = models.BooleanField(default=True)
#     history = HistoricalRecords()
#
#     def save(self, *args, **kwargs):
#         if 'user' in kwargs:
#             self._history_user = kwargs.pop('user')
#         super().save(*args, **kwargs)
#         if self.pk is None:  # New reservation
#             Notification.objects.create(
#                 user=self.user,
#                 message=f"Your reservation for '{self.book.title}' at {self.centre.name} has been recorded.",
#                 content_type=ContentType.objects.get_for_model(self),
#                 object_id=self.id
#             )
#
#     def __str__(self):
#         return f"{self.user.username} reserved {self.book.title}"
#
# class Notification(models.Model):
#     user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='notifications')
#     message = models.TextField()
#     created_at = models.DateTimeField(auto_now_add=True)
#     is_read = models.BooleanField(default=False)
#     responded_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='responded_notifications')
#     content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
#     object_id = models.PositiveIntegerField(null=True, blank=True)
#     related_object = GenericForeignKey('content_type', 'object_id')
#
#     class Meta:
#         ordering = ['-created_at']
#
#     def __str__(self):
#         return f"Notification for {self.user.username}: {self.message}"
