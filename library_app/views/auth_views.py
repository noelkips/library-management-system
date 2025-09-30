from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout, update_session_auth_hash, authenticate, login
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import csv
import openpyxl
from io import TextIOWrapper
from ..models import Book, Centre, CustomUser, Student 
from django.contrib.auth import update_session_auth_hash
# library_app/views/user_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.crypto import get_random_string

def is_site_admin(user):
    return user.is_site_admin

def is_librarian(user):
    return user.is_librarian

def is_authorized_for_manage_users(user):
    return user.is_site_admin or user.is_librarian

def can_reset_password(user, target_user):
    if user.is_site_admin:
        return True
    if user.is_librarian:
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
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'auth/login.html')

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('login')


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
            if user.is_superuser or user.is_librarian:
                centre_id = request.POST.get('centre')
                user.centre = Centre.objects.get(id=centre_id) if centre_id else None
            user.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('profile')
        except Exception as e:
            messages.error(request, f"Error updating profile: {str(e)}")
    centres = Centre.objects.all() if request.user.is_superuser or request.user.is_librarian else []
    return render(request, 'auth/profile.html', {'centres': centres})




@login_required
def change_password(request):
    if request.method == 'POST':
        try:
            current_password = request.POST.get('current_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            # Verify current password
            user = authenticate(request, email=request.user.email, password=current_password)
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
            user.save()
            update_session_auth_hash(request, user)  # Keep user logged in
            messages.success(request, "Password changed successfully.")
            return redirect('profile')
        except Exception as e:
            messages.error(request, f"Error changing password: {str(e)}")
    return render(request, 'auth/change_password.html')



@login_required
@user_passes_test(is_authorized_for_manage_users)
def manage_users(request):
    users = CustomUser.objects.all()
    centres = Centre.objects.all()
    groups = Group.objects.all()
    permissions = Permission.objects.all()
    return render(request, 'auth/manage_users.html', {
        'users': users,
        'centres': centres,
        'groups': groups,
        'permissions': permissions
    })

@login_required
@user_passes_test(is_authorized_for_manage_users)
def user_add(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = get_random_string(length=12)
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        centre_id = request.POST.get('centre')
        is_librarian = request.POST.get('is_librarian') == 'on'
        is_student = request.POST.get('is_student') == 'on'
        is_teacher = request.POST.get('is_teacher') == 'on'
        is_site_admin = request.POST.get('is_site_admin') == 'on'
        is_other = request.POST.get('is_other') == 'on'
        groups = request.POST.getlist('groups')
        errors = []

        if not email:
            errors.append("Email is required.")
        if CustomUser.objects.filter(email=email).exists():
            errors.append("Email is already in use.")
        if centre_id and centre_id != '' and not Centre.objects.filter(id=centre_id).exists():
            errors.append("Invalid centre selected.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            with transaction.atomic():
                centre = Centre.objects.get(id=centre_id) if centre_id and centre_id != '' else None
                user = CustomUser.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    centre=centre,
                    is_librarian=is_librarian,
                    is_student=is_student,
                    is_teacher=is_teacher,
                    is_site_admin=is_site_admin,
                    is_other=is_other,
                )
                if groups:
                    user.groups.set(groups)
                Notification.objects.create(
                    user=user,
                    message=f"Your new password is: {password}"
                )
                messages.success(request, "User added successfully. New password displayed in their dashboard.")
                return redirect('manage_users')
    return redirect('manage_users')

@login_required
@user_passes_test(is_authorized_for_manage_users)
def user_update(request, pk):
    target_user = get_object_or_404(CustomUser, pk=pk)
    if request.method == 'POST':
        email = request.POST.get('email')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        centre_id = request.POST.get('centre')
        is_librarian = request.POST.get('is_librarian') == 'on'
        is_student = request.POST.get('is_student') == 'on'
        is_teacher = request.POST.get('is_teacher') == 'on'
        is_site_admin = request.POST.get('is_site_admin') == 'on'
        is_other = request.POST.get('is_other') == 'on'
        groups = request.POST.getlist('groups')
        errors = []

        if not email:
            errors.append("Email is required.")
        if CustomUser.objects.filter(email=email).exclude(id=pk).exists():
            errors.append("Email is already in use.")
        if centre_id and centre_id != '' and not Centre.objects.filter(id=centre_id).exists():
            errors.append("Invalid centre selected.")

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
                target_user.is_librarian = is_librarian
                target_user.is_student = is_student
                target_user.is_teacher = is_teacher
                target_user.is_site_admin = is_site_admin
                target_user.is_other = is_other
                target_user.save()
                target_user.groups.clear()
                if groups:
                    target_user.groups.set(groups)
                messages.success(request, "User updated successfully.")
            return redirect('manage_users')
    return redirect('manage_users')

@login_required
@user_passes_test(is_authorized_for_manage_users)
def user_delete(request, pk):
    target_user = get_object_or_404(CustomUser, pk=pk)
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
def user_reset_password(request, pk):
    target_user = get_object_or_404(CustomUser, pk=pk)
    if not can_reset_password(request.user, target_user):
        messages.error(request, "You do not have permission to reset this user's password.")
        return redirect('manage_users')

    if request.method == 'POST':
        new_password = get_random_string(length=12)
        target_user.set_password(new_password)
        target_user.save()
        Notification.objects.create(
            user=target_user,
            message=f"Your password has been reset by {request.user.email}. New password: {new_password}"
        )
        messages.success(request, "Password reset successfully. New password displayed in the user's dashboard.")
        return redirect('manage_users')
    return redirect('manage_users')






