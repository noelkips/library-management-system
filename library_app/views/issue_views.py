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

        if book and book.available_copies < 1:
            errors.append("No available copies of this book.")
        if student and not student.user:
            errors.append("This student is not linked to a user account.")
        if student and student.user and student.user.borrows.filter(is_returned=False).count() >= 1:
            errors.append("This student already has a book borrowed.")
        if centre and book and centre != book.centre:
            errors.append("The selected book does not belong to the selected centre.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            with transaction.atomic():
                # Ensure available_copies is checked and updated atomically
                if book.available_copies <= 0:
                    messages.error(request, "No available copies of this book.")
                    return redirect('issue_book')
                user = student.user
                issue = Issue.objects.create(
                    book=book,
                    user=Student.objects.get(pk=student_id),
                    centre=centre,
                    issued_by=request.user
                )
                borrow = Borrow.objects.create(
                    book=book,
                    user=user,
                    centre=centre,
                    issued_by=request.user,
                    due_date=timezone.now() + timedelta(days=3)
                )
                borrow.save(from_issue_view=True)  # Pass the flag to save method
                # Update available_copies only if it's positive
                book.available_copies = max(0, book.available_copies - 1)  # Prevent negative values
                book.save()
                Notification.objects.create(
                    user=user,
                    message=f"Book '{book.title}' issued to you by {request.user.email} at {centre.name}. Due date: {(timezone.now() + timedelta(days=3)).strftime('%Y-%m-%d')}"
                )
                messages.success(request, f"Book '{book.title}' issued successfully to {student.name}.")
                return redirect('issue_list')

    if request.user.is_librarian:
        books = Book.objects.filter(is_active=True, available_copies__gt=0, centre=request.user.centre)
    else:
        books = Book.objects.filter(is_active=True, available_copies__gt=0)
    
    students = Student.objects.filter(user__isnull=False)  # Only students with linked user accounts
    centres = Centre.objects.all()
    return render(request, 'issue/issue_book.html', {
        'books': books,
        'students': students,
        'centres': centres
    })

@login_required
@user_passes_test(is_librarian_or_superuser)
def issue_list(request):
    issues = Issue.objects.select_related('book', 'user', 'centre', 'issued_by').all()
    
    # Add is_returned status to each issue by checking related Borrow
    for issue in issues:
        try:
            borrow = Borrow.objects.get(
                book=issue.book,
                user=issue.user.user,
                borrow_date__gte=issue.issue_date,
                borrow_date__lte=issue.issue_date + timedelta(minutes=1)
            )
            issue.is_returned = borrow.is_returned
        except Borrow.DoesNotExist:
            issue.is_returned = False
    
    return render(request, 'issue/issue_list.html', {'issues': issues})

@login_required
@user_passes_test(is_librarian_or_superuser)
def return_book(request, issue_id):
    if request.method == 'POST':
        issue = get_object_or_404(Issue, id=issue_id)
        
        try:
            with transaction.atomic():
                # Find the corresponding Borrow record
                borrow = Borrow.objects.get(
                    book=issue.book,
                    user=issue.user.user,
                    is_returned=False,
                    borrow_date__gte=issue.issue_date,
                    borrow_date__lte=issue.issue_date + timedelta(minutes=1)
                )
                
                # Mark as returned
                borrow.is_returned = True
                borrow.return_date = timezone.now()
                borrow.save()
                
                # Increment available copies
                issue.book.available_copies += 1
                issue.book.save()
                
                # Create notification
                Notification.objects.create(
                    user=issue.user.user,
                    message=f"Book '{issue.book.title}' returned successfully on {borrow.return_date.strftime('%Y-%m-%d')}."
                )
                
                messages.success(request, f"Book '{issue.book.title}' returned successfully by {issue.user.name}.")
        except Borrow.DoesNotExist:
            messages.error(request, "No active borrow record found for this issue.")
        except Exception as e:
            messages.error(request, f"Error returning book: {str(e)}")
    
    return redirect('issue_list')
