from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout, update_session_auth_hash, authenticate, login
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.utils import timezone
import csv
import openpyxl
from io import TextIOWrapper
from ..models import Book, Centre, CustomUser, School, Student
from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.crypto import get_random_string
from django.utils.safestring import mark_safe
import random


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

def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('email')  # Note: field is still 'email' in form, but backend handles child_ID
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.force_password_change:
                messages.info(request, "Please change your password before proceeding.")
                return redirect('change_password')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'auth/login.html')

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('login_view')

@login_required
def dashboard(request):
    context = {
        'user': request.user,
        'is_superuser': request.user.is_superuser,
        'is_librarian': request.user.is_librarian,
        'is_student': request.user.is_student,
        'is_teacher': request.user.is_teacher,
    }

    if request.user.is_superuser:
        context.update({
            'total_books': Book.objects.count(),
            'total_centres': Centre.objects.count(),
            'total_users': CustomUser.objects.count(),
            'total_students': Student.objects.count(),
            'total_issues': 0,  
            'total_borrows': 0,  
            'total_reservations': 0,  
            'total_notifications': 0,  
        })
    elif request.user.is_librarian and request.user.centre:
        context.update({
            'total_books': Book.objects.filter(centre=request.user.centre).count(),
            'total_students': Student.objects.filter(centre=request.user.centre).count(),
            'total_issues': 0,  
            'total_borrows': 0,  
            'total_reservations': 0,  
            'total_notifications': 0,  
        })
    elif request.user.is_student or request.user.is_teacher:
        context.update({
            'borrowed_books': [], 
            'notifications': [], 
        })
    else:
        context.update({
            'message': "Welcome to LibraryHub! Please contact an administrator for access."
        })

    return render(request, 'auth/dashboard.html', context)

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



@login_required
@user_passes_test(is_authorized_for_manage_users)
def manage_users(request):
    query = request.GET.get('q', '')
    centre_filter = request.GET.get('centre', '')
    role_filter = request.GET.get('role', '')
    
    if is_site_admin(request.user):
        # Site admin can see all users
        users = CustomUser.objects.all()
        
        # Apply search filter
        if query:
            users = users.filter(
                Q(email__icontains=query) | 
                Q(student_profile__child_ID__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            )
        
        # Apply centre filter
        if centre_filter:
            users = users.filter(centre_id=centre_filter)
        
        # Apply role filter
        if role_filter:
            if role_filter == 'student':
                users = users.filter(is_student=True)
            elif role_filter == 'librarian':
                users = users.filter(is_librarian=True)
            elif role_filter == 'teacher':
                users = users.filter(is_teacher=True)
            elif role_filter == 'site_admin':
                users = users.filter(is_site_admin=True)
            elif role_filter == 'other':
                users = users.filter(is_other=True)
        
        centres = Centre.objects.all()
        schools = []  # Schools will be loaded dynamically via AJAX
        
    else:
        # Librarian - only show students in their centre
        users = CustomUser.objects.filter(centre=request.user.centre, is_student=True)
        
        # Apply search filter
        if query:
            users = users.filter(
                Q(email__icontains=query) | 
                Q(student_profile__child_ID__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            )
        
        centres = [request.user.centre] if request.user.centre else []
        # Get schools for the librarian's centre
        schools = request.user.centre.school_set.all() if request.user.centre else []
    
    # Order users by email for consistent display
    users = users.order_by('email')
    
    return render(request, 'auth/manage_users.html', {
        'users': users,
        'centres': centres,
        'schools': schools,
        'is_full_admin': is_site_admin(request.user),
        'query': query,
    })


@login_required
@user_passes_test(is_authorized_for_manage_users)
def user_add(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        centre_id = request.POST.get('centre')
        is_librarian_flag = request.POST.get('is_librarian') == 'on'
        is_student = request.POST.get('is_student') == 'on'
        is_teacher = request.POST.get('is_teacher') == 'on'
        is_site_admin_flag = request.POST.get('is_site_admin') == 'on'
        is_other = request.POST.get('is_other') == 'on'
        errors = []

        # ✅ Only validate email if NOT student
        if not is_student:
            if not email:
                errors.append("Email is required.")
            elif CustomUser.objects.filter(email=email).exists():
                errors.append("Email is already in use.")

        if centre_id and centre_id != '' and not Centre.objects.filter(id=centre_id).exists():
            errors.append("Invalid centre selected.")

        # Role restrictions for librarians
        if is_librarian(request.user) and not is_site_admin(request.user):
            if not is_student or any([is_librarian_flag, is_teacher, is_site_admin_flag, is_other]):
                errors.append("Librarians can only add students.")
            if centre_id != str(request.user.centre.id):
                errors.append("Librarians can only add users to their own centre.")

        # Handle student specific fields
        child_ID = None
        school_id = request.POST.get('school', None)
        if is_student:
            child_ID = request.POST.get('child_ID')
            if not child_ID:
                errors.append("child_ID is required for students.")
            else:
                try:
                    child_ID = int(child_ID)
                    if Student.objects.filter(child_ID=child_ID).exists():
                        errors.append("child_ID is already in use.")
                except ValueError:
                    errors.append("Invalid child_ID.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            with transaction.atomic():
                centre = Centre.objects.get(id=centre_id) if centre_id and centre_id != '' else None

                if is_student:
                    school = School.objects.get(id=school_id) if school_id else None
                    school = school.name if school else "Mohi"
                    auto_email = f"{school}@{child_ID}.mohiafrica.org"
                    user = CustomUser(
                        email=auto_email,
                        first_name=first_name,
                        last_name=last_name,
                        centre=centre,
                        is_student=True,
                    )
                    child_ID_str = str(child_ID)
                    user.set_password(child_ID_str)  # initial password = child_ID
                    user.force_password_change = True
                    user._child_ID = child_ID  # temporary attributes for signal
                    user._school_id = school_id
                    user.save()

                    messages.success(
                        request,
                        mark_safe(
                            f"Student added successfully. "
                            f"Initial password is their child_ID: <span class=\"font-bold text-danger\">{child_ID_str}</span>. "
                            f"They will be forced to change it on first login."
                        )
                    )

                else:
                    # ✅ For non-students (staff, librarians, etc.)
                    random_digits = ''.join(random.choices('0123456789', k=5))
                    password = f"Lib{random_digits}"

                    user = CustomUser.objects.create_user(
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name,
                        centre=centre,
                        is_librarian=is_librarian_flag,
                        is_teacher=is_teacher,
                        is_site_admin=is_site_admin_flag,
                        is_other=is_other,
                    )
                    user.force_password_change = True
                    user.save()

                    messages.success(
                        request,
                        mark_safe(
                            f"User added successfully. "
                            f"Initial password: <span class=\"font-bold text-danger\">{password}</span>. "
                            f"They will be forced to change it on first login."
                        )
                    )

                return redirect('manage_users')

    return redirect('manage_users')

@login_required
@user_passes_test(is_authorized_for_manage_users)
def user_update(request, pk):
    target_user = get_object_or_404(CustomUser, pk=pk)
    # Permission check for update
    if is_librarian(request.user) and not is_site_admin(request.user):
        if not target_user.is_student:
            messages.error(request, "You do not have permission to update this user.")
            return redirect('manage_users')
        if target_user.centre != request.user.centre:
            messages.error(request, "You can only update users in your own centre.")
            return redirect('manage_users')

    if request.method == 'POST':
        email = request.POST.get('email')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        centre_id = request.POST.get('centre')
        is_librarian_flag = request.POST.get('is_librarian') == 'on'
        is_student = request.POST.get('is_student') == 'on'
        is_teacher = request.POST.get('is_teacher') == 'on'
        is_site_admin_flag = request.POST.get('is_site_admin') == 'on'
        is_other = request.POST.get('is_other') == 'on'
        errors = []

        if not email:
            errors.append("Email is required.")
        if CustomUser.objects.filter(email=email).exclude(id=pk).exists():
            errors.append("Email is already in use.")
        if centre_id and centre_id != '' and not Centre.objects.filter(id=centre_id).exists():
            errors.append("Invalid centre selected.")

        # Role restrictions for librarians
        if is_librarian(request.user) and not is_site_admin(request.user):
            if not is_student or any([is_librarian_flag, is_teacher, is_site_admin_flag, is_other]):
                errors.append("Librarians can only manage students.")
            if centre_id != str(request.user.centre.id):
                errors.append("Librarians can only assign to their own centre.")

        if is_student:
            child_ID = request.POST.get('child_ID')
            if not child_ID:
                errors.append("child_ID is required for students.")
            else:
                try:
                    child_ID = int(child_ID)
                    if Student.objects.filter(child_ID=child_ID).exclude(user=target_user).exists():
                        errors.append("child_ID is already in use.")
                except ValueError:
                    errors.append("Invalid child_ID.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            with transaction.atomic():
                centre = Centre.objects.get(id=centre_id) if centre_id and centre_id != '' else None
                target_user.email = email
                target_user.first_name = first_name
                target_user.last_name = last_name
                target_user.centre = centre
                target_user.is_librarian = is_librarian_flag
                target_user.is_student = is_student
                target_user.is_teacher = is_teacher
                target_user.is_site_admin = is_site_admin_flag
                target_user.is_other = is_other
                target_user.save()

                if is_student:
                    student, created = Student.objects.get_or_create(user=target_user)
                    student.child_ID = child_ID
                    student.name = f"{first_name} {last_name}"
                    student.centre = centre
                    student.school = request.POST.get('school', '')
                    student.save()

                messages.success(request, "User updated successfully.")
            return redirect('manage_users')
    return redirect('manage_users')

@login_required
@user_passes_test(is_authorized_for_manage_users)
def user_reset_password(request, pk):
    target_user = get_object_or_404(CustomUser, pk=pk)
    if not can_reset_password(request.user, target_user):
        messages.error(request, "You do not have permission to reset this user's password.")
        return redirect('manage_users')

    if is_librarian(request.user) and not is_site_admin(request.user):
        if target_user.centre != request.user.centre:
            messages.error(request, "You can only reset passwords for users in your own centre.")
            return redirect('manage_users')

    if request.method == 'POST':
        if target_user.is_student:
            try:
                student = target_user.student_profile
                new_password = str(student.child_ID)
            except Student.DoesNotExist:
                random_digits = ''.join(random.choices('0123456789', k=5))
                new_password = f"Lib{random_digits}"
        else:
            random_digits = ''.join(random.choices('0123456789', k=5))
            new_password = f"Lib{random_digits}"
        target_user.set_password(new_password)
        target_user.force_password_change = True
        target_user.save()
        messages.success(request, mark_safe(f"Password reset successfully. New password: <span class=\"font-bold text-danger\">{new_password}</span>. The user will be forced to change it on next login."))
        return redirect('manage_users')
    return redirect('manage_users')