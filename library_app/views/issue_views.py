from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from datetime import timedelta
from ..models import Book, CustomUser, Centre, Issue, Borrow, Notification, Student

def is_librarian_or_superuser(user):
    return user.is_librarian or user.is_superuser

@login_required
@user_passes_test(is_librarian_or_superuser)
def issue_book(request):
    if request.method == 'POST':
        book_id = request.POST.get('book')
        student_id = request.POST.get('student')
        centre_id = request.POST.get('centre')
        errors = []

        if not book_id:
            errors.append("Book is required.")
        if not student_id:
            errors.append("Student is required.")
        if not centre_id:
            errors.append("Centre is required.")

        book = get_object_or_404(Book, id=book_id) if book_id else None
        student = get_object_or_404(Student, id=student_id) if student_id else None
        centre = get_object_or_404(Centre, id=centre_id) if centre_id else None

        if book and not book.available_copies:
            errors.append("This book is not available.")
        if student and not student