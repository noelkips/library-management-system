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



