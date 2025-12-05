from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import logout, authenticate, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, Permission
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.safestring import mark_safe
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse
from ..utils import send_custom_email


from io import TextIOWrapper
from datetime import timedelta
from collections import defaultdict
import csv
import openpyxl
import random
import json

# UPDATED IMPORTS to include Grade and Subject
from ..models import (
    Book,
    Centre,
    CustomUser,
    School,
    Student,
    Borrow,
    Reservation,
    Notification,
    TeacherBookIssue,
    Grade,
    Subject
)


def is_site_admin(user):
    return user.is_site_admin or user.is_superuser

def is_librarian(user):
    return user.is_librarian

def is_authorized_for_manage_users(user):
    return is_site_admin(user) or is_librarian(user)

def can_reset_password(user, target_user):
    if is_site_admin(user):
        return True
    if is_librarian(user):
        return target_user.is_student or target_user.is_other or target_user.is_teacher
    return False

def can_user_borrow(user):
    """
    Determine whether a student user can borrow more books.
    Uses settings.MAX_BORROWS_PER_STUDENT (default 3) and counts currently issued borrows.
    Returns False for non-authenticated or non-student users.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    if not getattr(user, 'is_student', False):
        return False

    max_borrows = getattr(settings, 'MAX_BORROWS_PER_STUDENT', 1)
    active_issued = Borrow.objects.filter(user=user, status='issued').count()
    return active_issued < max_borrows

def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")  # can be email or CIN
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, "Login successful! Welcome back.")
            return redirect("dashboard")  # update to your home/dashboard URL
        else:
            messages.error(request, "Invalid credentials. Please try again.")
            return redirect("login_view")
            
    return render(request, "auth/login.html")


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('login_view')

@login_required
def dashboard(request):
    user = request.user
    context = {
        'user': user,
        'is_superuser': user.is_superuser,
        'is_librarian': user.is_librarian,
        'is_student': user.is_student,
        'is_teacher': user.is_teacher,
        'is_other': user.is_other,
    }

    # ------------------------------------------------------------------
    # 1. Super-user (admin) – system-wide stats
    # ------------------------------------------------------------------
    if user.is_superuser:
        # Centre stats: count TeacherBookIssue via teacher__centre
        centre_stats = Centre.objects.annotate(
            book_count=Count('books', distinct=True),
            student_count=Count('student', distinct=True),
            borrow_count=Count('borrows', distinct=True),
            issue_count=Count(
                'customuser__books_issued_to_students',
                filter=Q(customuser__is_teacher=True),
                distinct=True
            )
        ).order_by('-borrow_count')[:5]

        context.update({
            'total_books': Book.objects.count(),
            'total_centres': Centre.objects.count(),
            'total_users': CustomUser.objects.count(),
            'total_students': Student.objects.count(),
            'total_borrows': Borrow.objects.count(),
            'total_teacher_issues': TeacherBookIssue.objects.count(),
            'total_reservations': Reservation.objects.count(),
            # NEW STATS for Grade/Subject
            'total_grades': Grade.objects.count(),
            'total_subjects': Subject.objects.count(),

            # Borrow stats (only from Borrow)
            'active_borrows': Borrow.objects.filter(status='issued').count(),
            'overdue_borrows': Borrow.objects.filter(
                status='issued',
                due_date__lt=timezone.now()
            ).count(),
            'pending_requests': Borrow.objects.filter(status='requested').count(),
            'available_books': Book.objects.filter(available_copies=True).count(),

            # Recent activity
            'recent_borrows': Borrow.objects.select_related('user', 'book', 'centre')
                              .order_by('-request_date')[:5],

            # Centre stats (fixed)
            'centre_stats': centre_stats,
        })

        # Charts
        monthly_data = get_monthly_borrow_trends()
        context.update({
            'monthly_labels': json.dumps(monthly_data['labels']),
            'monthly_data': json.dumps(monthly_data['data']),
        })

        category_data = get_category_distribution()
        context.update({
            'category_labels': json.dumps(category_data['labels']),
            'category_data': json.dumps(category_data['data']),
        })

        centre_performance = get_centre_performance()
        context.update({
            'centre_labels': json.dumps(centre_performance['labels']),
            'centre_data': json.dumps(centre_performance['borrows']),
        })

        context['top_borrowed_books'] = get_top_borrowed_books()

    # ------------------------------------------------------------------
    # 2. Librarian – centre-specific view
    # ------------------------------------------------------------------
    elif user.is_librarian and user.centre:
        centre = user.centre

        context.update({
            'centre': centre,
            'total_books': Book.objects.filter(centre=centre).count(),
            'total_students': Student.objects.filter(centre=centre).count(),
            'total_borrows': Borrow.objects.filter(centre=centre).count(),
            'total_teacher_issues': TeacherBookIssue.objects.filter(
                teacher__centre=centre
            ).count(),
            'total_reservations': Reservation.objects.filter(centre=centre).count(),

            # Borrow-specific
            'active_borrows': Borrow.objects.filter(centre=centre, status='issued').count(),
            'overdue_borrows': Borrow.objects.filter(
                centre=centre, status='issued', due_date__lt=timezone.now()
            ).count(),
            'pending_requests': Borrow.objects.filter(centre=centre, status='requested').count(),
            'available_books': Book.objects.filter(centre=centre, available_copies=True).count(),

            # Action lists
            'recent_borrows': Borrow.objects.filter(centre=centre)
                              .select_related('user', 'book').order_by('-request_date')[:5],

            'overdue_list': Borrow.objects.filter(
                centre=centre, status='issued', due_date__lt=timezone.now()
            ).select_related('user', 'book').order_by('due_date')[:5],

            'pending_list': Borrow.objects.filter(
                centre=centre, status='requested'
            ).select_related('user', 'book').order_by('-request_date')[:5],
        })

        # Centre charts
        monthly_data = get_monthly_borrow_trends(centre=centre)
        context.update({
            'monthly_labels': json.dumps(monthly_data['labels']),
            'monthly_data': json.dumps(monthly_data['data']),
        })

        category_data = get_category_distribution(centre=centre)
        context.update({
            'category_labels': json.dumps(category_data['labels']),
            'category_data': json.dumps(category_data['data']),
        })

    # ------------------------------------------------------------------
    # 3. Teacher – own borrows + student issues
    # ------------------------------------------------------------------
    elif user.is_teacher:
        teacher_borrows = Borrow.objects.filter(user=user)
        student_issues = TeacherBookIssue.objects.filter(teacher=user)

        context.update({
            'borrowed_books': teacher_borrows.filter(status='issued')
                             .select_related('book', 'centre').order_by('-issue_date'),

            'issued_to_students': student_issues.filter(status='issued')
                                  .select_related('book').order_by('-issue_date'),

            'total_borrowed': teacher_borrows.filter(status='issued').count(),
            'total_issued_to_students': student_issues.filter(status='issued').count(),
            'overdue_borrows': teacher_borrows.filter(
                status='issued', due_date__lt=timezone.now()
            ).count(),
            'overdue_student_issues': student_issues.filter(
                status='issued', expected_return_date__lt=timezone.now()
            ).count(),

            'unread_notifications': Notification.objects.filter(user=user, is_read=False).count(),
            'active_reservations': Reservation.objects.filter(
                user=user, status='pending'
            ).select_related('book'),
        })

    # ------------------------------------------------------------------
    # 4. Student – personal borrowing
    # ------------------------------------------------------------------
    elif user.is_student:
        student_borrows = Borrow.objects.filter(user=user)

        context.update({
            'borrowed_books': student_borrows.filter(status='issued')
                             .select_related('book', 'centre').order_by('-issue_date'),

            'total_borrowed': student_borrows.filter(status='issued').count(),
            'can_borrow_more': can_user_borrow(user),
            'overdue_borrows': student_borrows.filter(
                status='issued', due_date__lt=timezone.now()
            ).count(),

            'borrow_history': student_borrows.filter(status='returned')
                             .select_related('book').order_by('-return_date')[:5],

            'unread_notifications': Notification.objects.filter(user=user, is_read=False).count(),
            'active_reservations': Reservation.objects.filter(
                user=user, status='pending'
            ).select_related('book'),
        })
    # ------------------------------------------------------------------
    # 5. Other user types (e.g., staff) – basic info
    # ------------------------------------------------------------------
    elif user.is_other:
        other_borrows = Borrow.objects.filter(user=user)

        context.update({
            'borrowed_books': other_borrows.filter(status='issued')
                            .select_related('book', 'centre').order_by('-issue_date'),

            'total_borrowed': other_borrows.filter(status='issued').count(),
            'can_borrow_more': can_user_borrow(user),
            'overdue_borrows': other_borrows.filter(
                status='issued', due_date__lt=timezone.now()
            ).count(),

            'borrow_history': other_borrows.filter(status='returned')
                            .select_related('book').order_by('-return_date')[:5],

            'unread_notifications': Notification.objects.filter(user=user, is_read=False).count(),
            'active_reservations': Reservation.objects.filter(
                user=user, status='pending'
            ).select_related('book'),
        })

    # ------------------------------------------------------------------
    # 5. Fallback
    # ------------------------------------------------------------------
    else:
        context['message'] = "Please contact an administrator to assign your role."

    return render(request, 'auth/dashboard.html', context)


# ─────────────────────────────────────────────────────────────────────
# FIXED: Dashboard helper functions (works with Book → subject__category)
# ─────────────────────────────────────────────────────────────────────

def get_category_distribution(centre=None):
    """
    Get distribution of books by category via subject__category
    Returns dict with 'labels' and 'data' arrays
    """
    books_query = Book.objects.filter(is_active=True).select_related('subject__category')
    
    if centre:
        books_query = books_query.filter(centre=centre)
    
    # Correct join: Book → Subject → Category
    category_counts = books_query.values(
        'subject__category__name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:6]  # Top 6 categories

    labels = []
    data = []
    
    for item in category_counts:
        category_name = item['subject__category__name'] or 'Uncategorized'
        labels.append(category_name)
        data.append(item['count'])
    
    # Fallback if no books
    if not labels:
        labels = ['No Books Yet']
        data = [0]
    
    return {
        'labels': labels,
        'data': data
    }


def get_centre_performance():
    """
    Top centres by number of borrows
    """
    centres = Centre.objects.annotate(
        borrow_count=Count('borrows')
    ).order_by('-borrow_count')[:10]

    return {
        'labels': [c.name for c in centres],
        'borrows': [c.borrow_count for c in centres],
    }


def get_top_borrowed_books(limit=10):
    """
    Top borrowed books (with title, author, subject info)
    """
    return Book.objects.filter(is_active=True)\
        .annotate(borrow_count=Count('borrows'))\
        .filter(borrow_count__gt=0)\
        .select_related('subject', 'subject__category', 'subject__grade')\
        .order_by('-borrow_count')[:limit]


def get_monthly_borrow_trends(centre=None):
    """
    Monthly borrow trends for last 6 months
    """
    from collections import defaultdict
    now = timezone.now()
    six_months_ago = now - timedelta(days=180)
    
    borrows = Borrow.objects.filter(request_date__gte=six_months_ago)
    if centre:
        borrows = borrows.filter(centre=centre)
    
    monthly_counts = defaultdict(int)
    for b in borrows:
        key = b.request_date.strftime('%Y-%m')
        monthly_counts[key] += 1
    
    labels = []
    data = []
    current = now.replace(day=1)
    for i in range(5, -1, -1):
        month_date = (current - timedelta(days=30 * i))
        key = month_date.strftime('%Y-%m')
        label = month_date.strftime('%b %Y')
        labels.append(label)
        data.append(monthly_counts.get(key, 0))
    
    return {'labels': labels, 'data': data}

@login_required
def profile(request):
    if request.method == 'POST':
        try:
            user = request.user
            user.first_name = request.POST.get('first_name', user.first_name)
            user.last_name = request.POST.get('last_name', user.last_name)
            email = request.POST.get('email')
            if email and email != user.email:
                if CustomUser.objects.filter(email=email).exists():
                    messages.error(request, "Email is already in use.")
                    return redirect('profile')
                user.email = email
            if user.is_superuser or user.is_site_admin:
                centre_id = request.POST.get('centre')
                user.centre = Centre.objects.get(id=centre_id) if centre_id else None
            user.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('profile')
        except Exception as e:
            messages.error(request, f"Error updating profile: {str(e)}")
    centres = Centre.objects.all() if request.user.is_superuser or request.user.is_site_admin else []
    return render(request, 'auth/profile.html', {'centres': centres})

@login_required
def change_password(request):
    if request.method == 'POST':
        try:
            current_password = request.POST.get('current_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            # Verify current password
            user = authenticate(request, username=request.user.email, password=current_password)
            if user is None:
                messages.error(request, "Current password is incorrect.")
                return redirect('change_password')

            # Validate new password
            if new_password != confirm_password:
                messages.error(request, "New password and confirmation do not match.")
                return redirect('change_password')

            if len(new_password) < 8:
                messages.error(request, "New password must be at least 8 characters long.")
                return redirect('change_password')

            # Update password
            user.set_password(new_password)
            user.force_password_change = False
            user.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Password changed successfully.")
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f"Error changing password: {str(e)}")
    return render(request, 'auth/change_password.html')

@login_required
@user_passes_test(is_authorized_for_manage_users)
def user_delete(request, pk):
    target_user = get_object_or_404(CustomUser, pk=pk)
    if is_librarian(request.user) and not is_site_admin(request.user):
        if not (target_user.is_student or target_user.is_teacher or target_user.is_other):
            messages.error(request, "You do not have permission to delete this user.")
            return redirect('manage_users')
        if target_user.centre != request.user.centre:
            messages.error(request, "You can only delete users in your own centre.")
            return redirect('manage_users')

    if request.method == 'POST':
        if target_user == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect('manage_users')
        with transaction.atomic():
            target_user.delete()
            messages.success(request, "User deleted successfully.")
        return redirect('manage_users')
    return redirect('manage_users')
# views/auth_views.py

@login_required
@user_passes_test(is_authorized_for_manage_users)
def manage_users(request):
    users = CustomUser.objects.filter(is_student=False).select_related('centre').order_by('first_name')

    query = request.GET.get('q', '').strip()
    if query:
        users = users.filter(
            Q(login_id__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )

    if not request.user.is_superuser:
        users = users.filter(centre=request.user.centre)

    centre_id = request.GET.get('centre')
    if centre_id:
        users = users.filter(centre_id=centre_id)

    role = request.GET.get('role')
    if role == 'librarian':
        users = users.filter(is_librarian=True)
    elif role == 'teacher':
        users = users.filter(is_teacher=True)
    elif role == 'site_admin':
        users = users.filter(is_site_admin=True)
    elif role == 'staff':
        users = users.filter(is_librarian=False, is_teacher=False, is_site_admin=False)

    paginator = Paginator(users, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'users': page_obj,
        'page_obj': page_obj,
        'query': query,
        'centres': Centre.objects.all() if request.user.is_superuser else [request.user.centre],
        'is_full_admin': request.user.is_superuser or request.user.is_site_admin,
    }
    return render(request, 'auth/manage_users.html', context)

@login_required
@user_passes_test(is_authorized_for_manage_users)
def user_add(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        centre_id = request.POST.get('centre')
        role = request.POST.get('role', 'staff')

        if not email or not centre_id:
            messages.error(request, "Email and Centre are required.")
            return redirect('manage_users')

        if CustomUser.objects.filter(login_id=email).exists():
            messages.error(request, "This login ID is already taken.")
            return redirect('manage_users')

        try:
            centre = Centre.objects.get(id=centre_id)
            with transaction.atomic():
                user = CustomUser.objects.create_user(
                    login_id=email,
                    email=email,
                    password=None,
                    first_name=first_name,
                    last_name=last_name,
                    centre=centre,
                    is_librarian=(role == 'librarian'),
                    is_teacher=(role == 'teacher'),
                    is_site_admin=(role == 'site_admin'),
                    is_student=False,
                    force_password_change=True,
                )
                user.set_unusable_password()
                user.save()

                # Generate login URL
                current_site = get_current_site(request)
                login_url = f"http://{current_site.domain}{reverse('login_view')}"

                # Role name for email
                role_name = {
                    'librarian': 'Librarian',
                    'teacher': 'Teacher',
                    'site_admin': 'Site Admin',
                    'staff': 'Staff Member'
                }.get(role, 'Staff Member')

                # Send Welcome Email
                subject = "Welcome to LibraryHub - Your Account is Ready!"
                message = f"""
                Hello {first_name or 'User'},

                Your LibraryHub account has been created!

                Role: {role_name}
                Centre: {centre.name}

                Login Details:
                • Login ID / Email: {email}
                • You will be asked to set a new password on first login

                Click here to log in and set your password:
                {login_url}

                If you did not request this account, please contact your librarian.

                Thank you!
                LibraryHub Team
                """

                send_custom_email(subject, message, [email])

                messages.success(request, f"User '{user.get_full_name() or email}' created and welcome email sent!")
            return redirect('manage_users')

        except Exception as e:
            messages.error(request, f"Error creating user: {str(e)}")
            return redirect('manage_users')

    return redirect('manage_users')

@login_required
@user_passes_test(is_authorized_for_manage_users)
def user_update(request, pk):
    user = get_object_or_404(CustomUser, pk=pk, is_student=False)
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        role = request.POST.get('role')  # 'librarian', 'teacher', 'site_admin', 'staff'

        if CustomUser.objects.filter(login_id=email).exclude(pk=user.pk).exists():
            messages.error(request, "This login ID is already in use.")
            return redirect('manage_users')

        try:
            centre = Centre.objects.get(id=request.POST.get('centre'))

            user.login_id = email
            user.email = email
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name = request.POST.get('last_name', '').strip()
            user.centre = centre

            # Just set the selected role — model will auto-handle is_other
            user.is_librarian = (role == 'librarian')
            user.is_teacher = (role == 'teacher')
            user.is_site_admin = (role == 'site_admin')
            # is_other is handled automatically in save()

            user.save()  # ← This triggers the magic

            messages.success(request, "User updated successfully.")
            return redirect('manage_users')

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return redirect('manage_users')


@login_required
@user_passes_test(is_authorized_for_manage_users)
def user_reset_password(request, pk):
    target_user = get_object_or_404(CustomUser, pk=pk)

    # Allow reset for both staff and students (different behavior)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                if target_user.is_student:
                    # === STUDENT: Reset password to child_ID and SHOW it ===
                    student = target_user.student_profile
                    new_password = str(student.child_ID)
                    target_user.set_password(new_password)
                    target_user.force_password_change = True
                    target_user.save()

                    messages.success(
                        request,
                        mark_safe(
                            f"Student password reset!<br>"
                            f"<strong>Login ID:</strong> {student.child_ID}<br>"
                            f"<strong>New Password:</strong> <code class='bg-gray-200 px-2 py-1 rounded'>{new_password}</code><br>"
                            f"They will be asked to change it on first login."
                        )
                    )
                else:
                    # === STAFF: Send secure reset link via email ===
                    token = default_token_generator.make_token(target_user)
                    uid = urlsafe_base64_encode(force_bytes(target_user.pk))
                    current_site = get_current_site(request)
                    reset_url = f"http://{current_site.domain}{reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})}"

                    subject = "LibraryHub - Password Reset Request"
                    message = f"""
                    Hello {target_user.get_full_name() or 'User'},

                    A password reset was requested for your LibraryHub account.

                    Click the link below to set a new password:
                    {reset_url}

                    This link expires in 24 hours.

                    If you didn't request this, ignore this email.

                    Thank you,
                    LibraryHub Team
                    """

                    if send_custom_email(subject, message, [target_user.email]):
                        messages.success(
                            request,
                            f"Password reset link sent to <strong>{target_user.email}</strong>"
                        )
                    else:
                        messages.error(request, "Failed to send email. Check server settings.")

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

        return redirect('manage_users')

    return redirect('manage_users')


def password_reset_request(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        if not email:
            messages.error(request, "Please enter an email address.")
            return render(request, 'accounts/password_reset_request.html')

        # Find all active, NON-STUDENT users with this email.
        associated_users = CustomUser.objects.filter(
            Q(email=email) & 
            Q(is_active=True) &
            Q(is_student=False)  # <-- This is your custom requirement
        )

        if not associated_users.exists():
            # Use a generic message for security
            messages.success(request, "If an account exists with that email, we've sent instructions to reset your password.")
            return redirect('password_reset_sent')
        
        # Send a reset link to all matching (non-student) users
        for user in associated_users:
            # Generate token and user ID
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Build the reset link
            current_site = request.get_host()
            relative_link = f'/accounts/reset/{uid}/{token}/'
            reset_url = f'http://{current_site}{relative_link}' # Use https in production

            # Create email content
            subject = 'Password Reset Request for MOHILibrary'
            
            # Use a template for the email body
            email_body = render_to_string('accounts/password_reset_email.txt', {
                'user': user,
                'reset_url': reset_url,
            })
            
            # Use your utility function to send the email
            send_custom_email(subject, email_body, [user.email])

        messages.success(request, "If an account exists with that email, we've sent instructions to reset your password.")
        return redirect('password_reset_sent')

    return render(request, 'accounts/password_reset_request.html')


def password_reset_sent(request):
    """
    A simple confirmation page.
    """
    return render(request, 'accounts/password_reset_sent.html')


def password_reset_confirm(request, uidb64=None, token=None):
    try:
        # Decode the user ID
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    # Check if the user exists and the token is valid
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            new_password1 = request.POST.get('new_password1')
            new_password2 = request.POST.get('new_password2')
            errors = []

            if not new_password1 or not new_password2:
                errors.append("Both password fields are required.")
            if new_password1 != new_password2:
                errors.append("New passwords do not match.")
            if len(new_password1) < 8:
                errors.append("New password must be at least 8 characters long.")
            
            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                user.set_password(new_password1)
                user.save()
                messages.success(request, "Password has been reset successfully. You can now log in.")
                return redirect('login_view') # Redirect to your login page name

        # GET request: show the password reset form
        return render(request, 'accounts/password_reset_new.html')
    else:
        # Invalid link
        messages.error(request, "The password reset link is invalid or has expired.")
        return render(request, 'accounts/password_reset_invalid.html')