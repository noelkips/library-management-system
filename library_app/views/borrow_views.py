from django.shortcuts import render, redirect
from django.contrib import messages
from ..models import Borrow, Book, Student
from django.utils import timezone

def borrow_add(request):
    if request.method == 'POST':
        student_id = request.POST.get('student')
        book_id = request.POST.get('book')
        try:
            student = Student.objects.get(id=student_id)
            book = Book.objects.get(id=book_id)
            if book.is_available:
                Borrow.objects.create(
                    student=student,
                    book=book,
                    borrow_date=timezone.now()
                )
                book.is_available = False
                book.save()
                messages.success(request, 'Book borrowed successfully!')
                return redirect('borrow_list')
            else:
                messages.error(request, 'Book is not available.')
        except (Student.DoesNotExist, Book.DoesNotExist):
            messages.error(request, 'Invalid student or book.')
    students = Student.objects.all()
    books = Book.objects.filter()
    return render(request, 'borrow/borrow_add.html', {'students': students, 'books': books})

def borrow_list(request):
    borrowings = Borrow.objects.filter(return_date__isnull=True)
    return render(request, 'borrow/borrow_list.html', {'borrowings': borrowings})