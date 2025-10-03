from django.shortcuts import render, redirect
from django.contrib import messages
from ..models import Borrow, Book, Student
from django.utils import timezone
from datetime import timedelta

def borrow_add(request):
    if request.method == 'POST':
        student_id = request.POST.get('student')
        book_id = request.POST.get('book')
        try:
            student = Student.objects.get(id=student_id)
            book = Book.objects.get(id=book_id)
            if book.available_copies > 0:
                Borrow.objects.create(
                    user=student.user,
                    book=book,
                    centre=request.user.centre,  # Added centre from logged-in user
                    issued_by=request.user,  # Added issued_by to track who processed the borrow
                    borrow_date=timezone.now(),
                    due_date=timezone.now() + timedelta(days=7)
                )
                messages.success(request, 'Book borrowed successfully!')
                return redirect('borrow_list')
            else:
                messages.error(request, 'Book is not available.')
        except (Student.DoesNotExist, Book.DoesNotExist):
            messages.error(request, 'Invalid student or book.')
    students = Student.objects.all()
    books = Book.objects.filter(available_copies__gt=0)
    return render(request, 'borrow/borrow_add.html', {'students': students, 'books': books})

def borrow_list(request):
    borrowings = Borrow.objects.filter(return_date__isnull=True)
    return render(request, 'borrow/borrow_list.html', {'borrowings': borrowings})
