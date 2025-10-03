from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count, Case, When, IntegerField
from django.core.paginator import Paginator
from datetime import timedelta
from .models import Book, Borrow, Reservation, Student, Centre, School, Notification, CustomUser
from .forms import BookForm, BorrowForm, ReservationForm  # You'll need to create these forms


# ==================== BOOK VIEWS ====================

@login_required
def book_list(request):
    """List all books with search and filter"""
    books = Book.objects.filter(is_active=True)
    
    # Filter by centre for librarians
    if request.user.is_librarian:
        books = books.filter(centre=request.user.centre)
    
    # Search functionality
    search = request.GET.get('search', '')
    if search:
        books = books.filter(
            Q(title__icontains=search) |
            Q(author__icontains=search) |
            Q(book_code__icontains=search) |
            Q(category__icontains=search)
        )
    
    # Filter by category
    category = request.GET.get('category', '')
    if category:
        books = books.filter(category=category)
    
    # Filter by centre (for admins)
    centre_id = request.GET.get('centre', '')
    if centre_id and request.user.is_site_admin:
        books = books.filter(centre_id=centre_id)
    
    # Filter by availability
    availability = request.GET.get('availability', '')
    if availability == 'available':
        books = books.filter(available_copies__gt=0)
    elif availability == 'unavailable':
        books = books.filter(available_copies=0)
    
    # Get all centres and categories for filters
    centres = Centre.objects.all()
    categories = Book.objects.values_list('category', flat=True).distinct()
    
    # Pagination
    paginator = Paginator(books, 20)
    page_number = request.GET.get('page')
    books = paginator.get_page(page_number)
    
    context = {
        'books': books,
        'centres': centres,
        'categories': categories,
    }
    return render(request, 'books/book_list.html', context)


@login_required
def book_detail(request, pk):
    """Show book details with transaction history"""
    book = get_object_or_404(Book, pk=pk)
    
    # Check permissions
    if request.user.is_librarian and book.centre != request.user.centre:
        messages.error(request, "You don't have permission to view this book.")
        return redirect('book_list')
    
    # Get borrow history
    borrows = Borrow.objects.filter(book=book).select_related(
        'user', 'issued_by', 'returned_to'
    ).order_by('-request_date')
    
    # Get active reservations
    reservations = Reservation.objects.filter(
        book=book, 
        status='pending'
    ).select_related('user').order_by('reservation_date')
    
    # Check if current user has active borrow or reservation
    user_active_borrow = None
    user_reservation = None
    
    if request.user.is_student:
        user_active_borrow = Borrow.objects.filter(
            book=book,
            user=request.user,
            status__in=['requested', 'issued']
        ).first()
        
        user_reservation = Reservation.objects.filter(
            book=book,
            user=request.user,
            status='pending'
        ).first()
    
    context = {
        'book': book,
        'borrows': borrows,
        'reservations': reservations,
        'user_active_borrow': user_active_borrow,
        'user_reservation': user_reservation,
    }
    return render(request, 'books/book_detail.html', context)


@login_required
def book_add(request):
    """Add a new book"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to add books.")
        return redirect('book_list')
    
    if request.method == 'POST':
        form = BookForm(request.POST)
        if form.is_valid():
            book = form.save(commit=False)
            book.added_by = request.user
            
            # Auto-assign centre for librarians
            if request.user.is_librarian:
                book.centre = request.user.centre
            
            book.save(user=request.user)
            messages.success(request, f"Book '{book.title}' added successfully!")
            return redirect('book_list')
    else:
        form = BookForm()
        
        # Restrict centre selection for librarians
        if request.user.is_librarian:
            form.fields['centre'].initial = request.user.centre
            form.fields['centre'].widget.attrs['disabled'] = True
    
    context = {'form': form}
    return render(request, 'books/book_add.html', context)


@login_required
def book_update(request, pk):
    """Update book details"""
    book = get_object_or_404(Book, pk=pk)
    
    # Check permissions
    if request.user.is_librarian and book.centre != request.user.centre:
        messages.error(request, "You don't have permission to edit this book.")
        return redirect('book_list')
    
    if request.method == 'POST':
        form = BookForm(request.POST, instance=book)
        if form.is_valid():
            book = form.save(commit=False)
            book.save(user=request.user)
            messages.success(request, f"Book '{book.title}' updated successfully!")
            return redirect('book_detail', pk=book.pk)
    else:
        form = BookForm(instance=book)
        
        # Restrict centre selection for librarians
        if request.user.is_librarian:
            form.fields['centre'].widget.attrs['disabled'] = True
    
    context = {'form': form, 'book': book}
    return render(request, 'books/book_update.html', context)


@login_required
def book_delete(request, pk):
    """Soft delete a book"""
    book = get_object_or_404(Book, pk=pk)
    
    # Check permissions
    if not request.user.is_site_admin:
        messages.error(request, "Only admins can delete books.")
        return redirect('book_list')
    
    if request.method == 'POST':
        book.is_active = False
        book.save(user=request.user)
        messages.success(request, f"Book '{book.title}' deleted successfully!")
        return redirect('book_list')
    
    return render(request, 'books/book_delete.html', {'book': book})


# ==================== BORROW VIEWS (STUDENT) ====================

@login_required
def borrow_request(request, book_id):
    """Student requests to borrow a book"""
    if not request.user.is_student:
        messages.error(request, "Only students can borrow books.")
        return redirect('book_list')
    
    book = get_object_or_404(Book, pk=book_id, is_active=True)
    student = request.user.student_profile
    
    # Check if student can borrow
    if not student.can_borrow():
        messages.error(request, "You already have an active borrow. Return it before borrowing another book.")
        return redirect('book_detail', pk=book_id)
    
    # Check if student already has active borrow for this book
    existing_borrow = Borrow.objects.filter(
        book=book,
        user=request.user,
        status__in=['requested', 'issued']
    ).first()
    
    if existing_borrow:
        messages.warning(request, "You already have an active request/borrow for this book.")
        return redirect('book_detail', pk=book_id)
    
    # Check if book is available
    if book.is_available():
        # Create borrow request
        borrow = Borrow.objects.create(
            book=book,
            user=request.user,
            centre=book.centre,
            status='requested',
            notes=request.POST.get('notes', '')
        )
        
        # Notify librarians
        librarians = CustomUser.objects.filter(
            is_librarian=True,
            centre=book.centre
        )
        for librarian in librarians:
            Notification.objects.create(
                user=librarian,
                message=f"{request.user.get_full_name()} requested to borrow '{book.title}'"
            )
        
        messages.success(request, f"Borrow request for '{book.title}' submitted! Wait for librarian approval.")
    else:
        # Book not available - create reservation
        reservation = Reservation.objects.create(
            book=book,
            user=request.user,
            centre=book.centre
        )
        messages.info(request, f"'{book.title}' is currently unavailable. You've been added to the reservation list.")
    
    return redirect('book_detail', pk=book_id)


@login_required
def my_borrows(request):
    """Student views their borrow history"""
    if not request.user.is_student:
        messages.error(request, "This page is for students only.")
        return redirect('book_list')
    
    # Get all borrows
    borrows = Borrow.objects.filter(user=request.user).select_related(
        'book', 'issued_by', 'returned_to'
    ).order_by('-request_date')
    
    # Separate active and history
    active_borrows = borrows.filter(status__in=['requested', 'issued'])
    history_borrows = borrows.filter(status='returned')
    
    # Get reservations
    reservations = Reservation.objects.filter(
        user=request.user,
        status='pending'
    ).select_related('book')
    
    context = {
        'active_borrows': active_borrows,
        'history_borrows': history_borrows,
        'reservations': reservations,
    }
    return render(request, 'borrows/my_borrows.html', context)


@login_required
def borrow_cancel(request, borrow_id):
    """Student cancels their borrow request"""
    borrow = get_object_or_404(Borrow, pk=borrow_id, user=request.user)
    
    if borrow.status != 'requested':
        messages.error(request, "You can only cancel pending requests.")
        return redirect('my_borrows')
    
    if request.method == 'POST':
        borrow.delete()
        messages.success(request, "Borrow request cancelled.")
        return redirect('my_borrows')
    
    return render(request, 'borrows/borrow_cancel.html', {'borrow': borrow})


@login_required
def borrow_renew(request, borrow_id):
    """Student requests to renew their borrow"""
    borrow = get_object_or_404(Borrow, pk=borrow_id, user=request.user)
    
    if borrow.status != 'issued':
        messages.error(request, "You can only renew issued books.")
        return redirect('my_borrows')
    
    if borrow.renew(user=request.user):
        messages.success(request, f"'{borrow.book.title}' renewed successfully! New due date: {borrow.due_date.strftime('%Y-%m-%d')}")
    else:
        messages.error(request, "Maximum renewals reached (2). Please return the book.")
    
    return redirect('my_borrows')


# ==================== BORROW VIEWS (LIBRARIAN) ====================

@login_required
def borrow_requests_list(request):
    """Librarian views pending borrow requests"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        return redirect('book_list')
    
    # Get pending requests
    requests_qs = Borrow.objects.filter(status='requested').select_related(
        'book', 'user', 'centre'
    )
    
    # Filter by centre for librarians
    if request.user.is_librarian:
        requests_qs = requests_qs.filter(centre=request.user.centre)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        requests_qs = requests_qs.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(book__title__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(requests_qs, 20)
    page_number = request.GET.get('page')
    borrow_requests = paginator.get_page(page_number)
    
    context = {'borrow_requests': borrow_requests}
    return render(request, 'borrows/borrow_requests_list.html', context)


@login_required
def borrow_issue(request, borrow_id):
    """Librarian issues a book (approves borrow request)"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to issue books.")
        return redirect('book_list')
    
    borrow = get_object_or_404(Borrow, pk=borrow_id)
    
    # Check permissions
    if request.user.is_librarian and borrow.centre != request.user.centre:
        messages.error(request, "You can only issue books from your centre.")
        return redirect('borrow_requests_list')
    
    if borrow.status != 'requested':
        messages.error(request, "This borrow request has already been processed.")
        return redirect('borrow_requests_list')
    
    # Check if book is still available
    if not borrow.book.is_available():
        messages.error(request, f"'{borrow.book.title}' is no longer available.")
        return redirect('borrow_requests_list')
    
    if request.method == 'POST':
        # Issue the book
        borrow.status = 'issued'
        borrow.issue_date = timezone.now()
        borrow.due_date = timezone.now() + timedelta(days=3)  # 3 days borrow period
        borrow.issued_by = request.user
        borrow.save(user=request.user)
        
        # Decrease available copies
        borrow.book.available_copies -= 1
        borrow.book.save(user=request.user)
        
        # Notify student
        Notification.objects.create(
            user=borrow.user,
            message=f"Your request for '{borrow.book.title}' has been approved! Due date: {borrow.due_date.strftime('%Y-%m-%d')}"
        )
        
        messages.success(request, f"Book '{borrow.book.title}' issued to {borrow.user.get_full_name()}!")
        return redirect('borrow_requests_list')
    
    context = {'borrow': borrow}
    return render(request, 'borrows/borrow_issue.html', context)


@login_required
def borrow_reject(request, borrow_id):
    """Librarian rejects a borrow request"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to reject requests.")
        return redirect('book_list')
    
    borrow = get_object_or_404(Borrow, pk=borrow_id)
    
    # Check permissions
    if request.user.is_librarian and borrow.centre != request.user.centre:
        messages.error(request, "You can only manage requests from your centre.")
        return redirect('borrow_requests_list')
    
    if borrow.status != 'requested':
        messages.error(request, "This borrow request has already been processed.")
        return redirect('borrow_requests_list')
    
    if request.method == 'POST':
        reason = request.POST.get('reason', 'No reason provided')
        
        # Notify student
        Notification.objects.create(
            user=borrow.user,
            message=f"Your request for '{borrow.book.title}' was rejected. Reason: {reason}"
        )
        
        # Delete the request
        book_title = borrow.book.title
        student_name = borrow.user.get_full_name()
        borrow.delete()
        
        messages.success(request, f"Borrow request for '{book_title}' by {student_name} rejected.")
        return redirect('borrow_requests_list')
    
    context = {'borrow': borrow}
    return render(request, 'borrows/borrow_reject.html', context)


@login_required
def active_borrows_list(request):
    """Librarian views all active borrows (issued books)"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        return redirect('book_list')
    
    # Get active borrows
    borrows = Borrow.objects.filter(status='issued').select_related(
        'book', 'user', 'issued_by', 'centre'
    )
    
    # Filter by centre for librarians
    if request.user.is_librarian:
        borrows = borrows.filter(centre=request.user.centre)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        borrows = borrows.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(book__title__icontains=search)
        )
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter == 'overdue':
        borrows = [b for b in borrows if b.is_overdue()]
    
    # Pagination
    paginator = Paginator(borrows, 20)
    page_number = request.GET.get('page')
    borrows = paginator.get_page(page_number)
    
    context = {'borrows': borrows}
    return render(request, 'borrows/active_borrows_list.html', context)


@login_required
def borrow_receive_return(request, borrow_id):
    """Librarian receives a returned book"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to receive returns.")
        return redirect('book_list')
    
    borrow = get_object_or_404(Borrow, pk=borrow_id)
    
    # Check permissions
    if request.user.is_librarian and borrow.centre != request.user.centre:
        messages.error(request, "You can only receive returns for your centre.")
        return redirect('active_borrows_list')
    
    if borrow.status != 'issued':
        messages.error(request, "This book is not currently issued.")
        return redirect('active_borrows_list')
    
    if request.method == 'POST':
        # Mark as returned
        borrow.status = 'returned'
        borrow.return_date = timezone.now()
        borrow.returned_to = request.user
        borrow.save(user=request.user)
        
        # Increase available copies
        borrow.book.available_copies += 1
        borrow.book.save(user=request.user)
        
        # Check for pending reservations
        pending_reservation = Reservation.objects.filter(
            book=borrow.book,
            status='pending'
        ).order_by('reservation_date').first()
        
        if pending_reservation:
            # Notify user with reservation
            Notification.objects.create(
                user=pending_reservation.user,
                message=f"'{borrow.book.title}' is now available! Your reservation is ready."
            )
            pending_reservation.notified = True
            pending_reservation.save()
        
        # Notify student
        Notification.objects.create(
            user=borrow.user,
            message=f"Thank you for returning '{borrow.book.title}'!"
        )
        
        messages.success(request, f"Book '{borrow.book.title}' returned by {borrow.user.get_full_name()}!")
        return redirect('active_borrows_list')
    
    context = {'borrow': borrow}
    return render(request, 'borrows/borrow_receive_return.html', context)


# ==================== RESERVATION VIEWS ====================

@login_required
def reservation_cancel(request, reservation_id):
    """Cancel a reservation"""
    reservation = get_object_or_404(Reservation, pk=reservation_id, user=request.user)
    
    if reservation.status != 'pending':
        messages.error(request, "This reservation is no longer active.")
        return redirect('my_borrows')
    
    if request.method == 'POST':
        reservation.status = 'cancelled'
        reservation.save()
        messages.success(request, f"Reservation for '{reservation.book.title}' cancelled.")
        return redirect('my_borrows')
    
    return render(request, 'reservations/reservation_cancel.html', {'reservation': reservation})


@login_required
def reservations_list(request):
    """Librarian views all reservations"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        return redirect('book_list')
    
    reservations = Reservation.objects.filter(status='pending').select_related(
        'book', 'user', 'centre'
    )
    
    # Filter by centre for librarians
    if request.user.is_librarian:
        reservations = reservations.filter(centre=request.user.centre)
    
    context = {'reservations': reservations}
    return render(request, 'reservations/reservations_list.html', context)