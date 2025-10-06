from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.core.paginator import Paginator
from datetime import timedelta
from ..models import (
    Book, Borrow, Reservation, Centre, Notification, 
    CustomUser, can_user_borrow, get_user_borrow_limit
)

# ==================== BORROW REQUEST (STUDENTS/TEACHERS/OTHER) ====================
@login_required
def borrow_request(request, book_id):
    """User requests to borrow a book"""
    if not (request.user.is_student or request.user.is_teacher or request.user.is_other):
        messages.error(request, "Only students, teachers, and other users can borrow books.")
        print(f"Unauthorized borrow attempt by {request.user.email} for book ID {book_id}")
        return redirect('book_list')
    
    book = get_object_or_404(Book, pk=book_id, is_active=True)
    
    # Check if user can borrow
    if not can_user_borrow(request.user):
        limit = get_user_borrow_limit(request.user)
        messages.error(request, f"You have reached your borrow limit of {limit} book{'s' if limit != 1 else ''}.")
        print(f"Borrow limit reached for {request.user.email} (limit: {limit})")
        return redirect('book_detail', pk=book_id)
    
    # Check if user already has active borrow/request for this book
    existing_borrow = Borrow.objects.filter(
        book=book,
        user=request.user,
        status__in=['requested', 'issued']
    ).first()
    
    if existing_borrow:
        messages.warning(request, "You already have an active request or borrow for this book.")
        print(f"Duplicate borrow attempt by {request.user.email} for book '{book.title}'")
        return redirect('book_detail', pk=book_id)
    
    if request.method == 'POST':
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
                    message=f"{request.user.get_full_name() or request.user.email} requested to borrow '{book.title}'"
                )
            
            messages.success(request, f"Borrow request for '{book.title}' submitted! Wait for librarian approval.", extra_tags='green')
            print(f"Borrow request created by {request.user.email} for '{book.title}' (ID: {book_id})")
        else:
            # Book not available - create reservation
            existing_reservation = Reservation.objects.filter(
                book=book,
                user=request.user,
                status='pending'
            ).first()
            
            if existing_reservation:
                messages.warning(request, "You already have a reservation for this book.")
                print(f"Duplicate reservation attempt by {request.user.email} for '{book.title}'")
            else:
                Reservation.objects.create(
                    book=book,
                    user=request.user,
                    centre=book.centre
                )
                messages.info(request, f"'{book.title}' is currently unavailable. You've been added to the reservation list.")
                print(f"Reservation created by {request.user.email} for '{book.title}'")
        return redirect('my_borrows')
    
    context = {'book': book}
    return render(request, 'borrows/borrow_request.html', context)

@login_required
def my_borrows(request):
    """User views their borrow history"""
    if not (request.user.is_student or request.user.is_teacher or request.user.is_other):
        messages.error(request, "This page is for borrowers only.")
        print(f"Unauthorized access to my_borrows by {request.user.email}")
        return redirect('book_list')
    
    # Get all borrows
    borrows = Borrow.objects.filter(user=request.user).select_related(
        'book', 'issued_by', 'returned_to', 'book__category'
    ).order_by('-request_date')
    
    # Separate active and history
    active_borrows = borrows.filter(status__in=['requested', 'issued'])
    history_borrows = borrows.filter(status='returned')[:20]
    
    # Get reservations
    reservations = Reservation.objects.filter(
        user=request.user,
        status='pending'
    ).select_related('book', 'book__category')
    
    # Get borrow limit info
    limit = get_user_borrow_limit(request.user)
    can_borrow_more = can_user_borrow(request.user)
    
    context = {
        'active_borrows': active_borrows,
        'history_borrows': history_borrows,
        'reservations': reservations,
        'borrow_limit': limit,
        'can_borrow_more': can_borrow_more,
    }
    print(f"User {request.user.email} viewed my_borrows: {active_borrows.count()} active, {history_borrows.count()} history")
    return render(request, 'borrows/my_borrows.html', context)

@login_required
def borrow_cancel(request, borrow_id):
    """User cancels their borrow request"""
    borrow = get_object_or_404(Borrow, pk=borrow_id, user=request.user)
    
    if borrow.status != 'requested':
        messages.error(request, "You can only cancel pending requests.")
        print(f"Invalid cancel attempt by {request.user.email} for borrow ID {borrow_id} (status: {borrow.status})")
        return redirect('my_borrows')
    
    if request.method == 'POST':
        book_title = borrow.book.title
        borrow.delete()
        messages.success(request, f"Borrow request for '{book_title}' cancelled.", extra_tags='green')
        print(f"Borrow request ID {borrow_id} cancelled by {request.user.email}")
        return redirect('my_borrows')
    
    context = {'borrow': borrow}
    return render(request, 'borrows/borrow_cancel.html', context)

@login_required
def borrow_renew(request, borrow_id):
    """User requests to renew their borrow"""
    borrow = get_object_or_404(Borrow, pk=borrow_id, user=request.user)
    
    if borrow.status != 'issued':
        messages.error(request, "You can only renew issued books.")
        print(f"Invalid renew attempt by {request.user.email} for borrow ID {borrow_id} (status: {borrow.status})")
        return redirect('my_borrows')
    
    if borrow.renew(user=request.user):
        messages.success(request, f"'{borrow.book.title}' renewed successfully! New due date: {borrow.due_date.strftime('%Y-%m-%d')}", extra_tags='green')
        print(f"Borrow ID {borrow_id} renewed by {request.user.email}, new due date: {borrow.due_date}")
    else:
        messages.error(request, "Maximum renewals reached (2). Please return the book.")
        print(f"Max renewals reached for borrow ID {borrow_id} by {request.user.email}")
    
    return redirect('my_borrows')

# ==================== LIBRARIAN VIEWS ====================

@login_required
def borrow_requests_list(request):
    """Librarian views pending borrow requests"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(f"Unauthorized access to borrow_requests_list by {request.user.email}")
        return redirect('book_list')
    
    # Get pending requests
    requests_qs = Borrow.objects.filter(status='requested').select_related(
        'book', 'user', 'centre', 'book__category'
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
            Q(book__title__icontains=search) |
            Q(book__book_code__icontains=search)
        )
    
    requests_qs = requests_qs.order_by('request_date')
    
    # Pagination
    paginator = Paginator(requests_qs, 20)
    page_number = request.GET.get('page')
    borrow_requests = paginator.get_page(page_number)
    
    context = {
        'borrow_requests': borrow_requests,
        'search': search,
    }
    print(f"Librarian {request.user.email} viewed borrow_requests_list: {requests_qs.count()} requests")
    return render(request, 'borrows/borrow_requests_list.html', context)
@login_required
def borrow_issue(request, borrow_id):
    """Librarian issues a book (approves borrow request)"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to issue books.")
        print(f"Unauthorized issue attempt by {request.user.email} for borrow ID {borrow_id}")
        return redirect('book_list')
    
    borrow = get_object_or_404(Borrow, pk=borrow_id)
    
    # Check permissions
    if request.user.is_librarian and borrow.centre != request.user.centre:
        messages.error(request, "You can only issue books from your centre.")
        print(f"Unauthorized issue attempt by {request.user.email} for borrow ID {borrow_id} (wrong centre)")
        return redirect('borrow_requests_list')
    
    if borrow.status != 'requested':
        messages.error(request, "This borrow request has already been processed.")
        print(f"Invalid issue attempt by {request.user.email} for borrow ID {borrow_id} (status: {borrow.status})")
        return redirect('borrow_requests_list')
    
    # Check if book is still available
    if not borrow.book.is_available():
        messages.error(request, f"'{borrow.book.title}' is no longer available.")
        print(f"Book '{borrow.book.title}' unavailable for borrow ID {borrow_id}")
        return redirect('borrow_requests_list')
    
    if request.method == 'POST':
        try:
            # Get custom due date or default to 3 days
            days = int(request.POST.get('days', 3))
            if days <= 0 or days > 30:
                messages.error(request, "Due date must be between 1 and 30 days.")
                print(f"Invalid days ({days}) for borrow ID {borrow_id} by {request.user.email}")
                return redirect('borrow_issue', borrow_id=borrow_id)
            
            due_date = timezone.now() + timedelta(days=days)
            if due_date.year > 2025:
                messages.error(request, "Due date cannot be set beyond 2025.")
                print(f"Due date beyond 2025 for borrow ID {borrow_id} by {request.user.email}")
                return redirect('borrow_issue', borrow_id=borrow_id)
            
            # Issue the book
            borrow.status = 'issued'
            borrow.issue_date = timezone.now()
            borrow.due_date = due_date
            borrow.issued_by = request.user
            borrow.save(user=request.user)
            
            # Decrease available copies
            borrow.book.available_copies -= 1
            borrow.book.save(user=request.user)
            
            # Notify user
            Notification.objects.create(
                user=borrow.user,
                message=f"Your request for '{borrow.book.title}' has been approved! Due date: {borrow.due_date.strftime('%Y-%m-%d')}"
            )
            
            messages.success(request, f"Book '{borrow.book.title}' issued to {borrow.user.get_full_name() or borrow.user.email}!", extra_tags='green')
            print(f"Borrow ID {borrow_id} issued by {request.user.email} to {borrow.user.email}")
            return redirect('borrow_requests_list')
        except ValueError:
            messages.error(request, "Invalid number of days provided.")
            print(f"ValueError: Invalid days input for borrow ID {borrow_id} by {request.user.email}")
    
    context = {'borrow': borrow}
    return render(request, 'borrows/borrow_issue.html', context)

@login_required
def borrow_reject(request, borrow_id):
    """Librarian rejects a borrow request"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to reject requests.")
        print(f"Unauthorized reject attempt by {request.user.email} for borrow ID {borrow_id}")
        return redirect('book_list')
    
    borrow = get_object_or_404(Borrow, pk=borrow_id)
    
    # Check permissions
    if request.user.is_librarian and borrow.centre != request.user.centre:
        messages.error(request, "You can only manage requests from your centre.")
        print(f"Unauthorized reject attempt by {request.user.email} for borrow ID {borrow_id} (wrong centre)")
        return redirect('borrow_requests_list')
    
    if borrow.status != 'requested':
        messages.error(request, "This borrow request has already been processed.")
        print(f"Invalid reject attempt by {request.user.email} for borrow ID {borrow_id} (status: {borrow.status})")
        return redirect('borrow_requests_list')
    
    if request.method == 'POST':
        reason = request.POST.get('reason', 'No reason provided')
        
        # Notify user
        Notification.objects.create(
            user=borrow.user,
            message=f"Your request for '{borrow.book.title}' was rejected. Reason: {reason}"
        )
        
        # Delete the request
        book_title = borrow.book.title
        user_name = borrow.user.get_full_name() or borrow.user.email
        borrow.delete()
        
        messages.success(request, f"Borrow request for '{book_title}' by {user_name} rejected.", extra_tags='green')
        print(f"Borrow ID {borrow_id} rejected by {request.user.email}, reason: {reason}")
        return redirect('borrow_requests_list')
    
    context = {'borrow': borrow}
    return render(request, 'borrows/borrow_reject.html', context)

@login_required
def active_borrows_list(request):
    """Librarian views all active borrows (issued books)"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(f"Unauthorized access to active_borrows_list by {request.user.email}")
        return redirect('book_list')
    
    # Get active borrows
    borrows = Borrow.objects.filter(status='issued').select_related(
        'book', 'user', 'issued_by', 'centre', 'book__category'
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
            Q(book__title__icontains=search) |
            Q(book__book_code__icontains=search)
        )
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter == 'overdue':
        borrows = [b for b in borrows if b.is_overdue()]
    
    borrows = list(borrows) if status_filter == 'overdue' else borrows.order_by('due_date')
    
    # Pagination
    paginator = Paginator(borrows, 20)
    page_number = request.GET.get('page')
    borrows_page = paginator.get_page(page_number)
    
    context = {
        'borrows': borrows_page,
        'search': search,
        'status_filter': status_filter,
    }
    print(f"Librarian {request.user.email} viewed active_borrows_list: {len(borrows)} borrows")
    return render(request, 'borrows/active_borrows_list.html', context)
@login_required
def borrow_receive_return(request, borrow_id):
    """Librarian receives a returned book"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to receive returns.")
        print(f"Unauthorized return attempt by {request.user.email} for borrow ID {borrow_id}")
        return redirect('book_list')
    
    borrow = get_object_or_404(Borrow, pk=borrow_id)
    
    # Check permissions
    if request.user.is_librarian and borrow.centre != request.user.centre:
        messages.error(request, "You can only receive returns for your centre.")
        print(f"Unauthorized return attempt by {request.user.email} for borrow ID {borrow_id} (wrong centre)")
        return redirect('active_borrows_list')
    
    if borrow.status != 'issued':
        messages.error(request, "This book is not currently issued.")
        print(f"Invalid return attempt by {request.user.email} for borrow ID {borrow_id} (status: {borrow.status})")
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
                message=f"'{borrow.book.title}' is now available! Your reservation is ready. Please request to borrow within 2 days."
            )
            pending_reservation.notified = True
            pending_reservation.save()
        
        # Notify user
        Notification.objects.create(
            user=borrow.user,
            message=f"Thank you for returning '{borrow.book.title}'!"
        )
        
        messages.success(request, f"Book '{borrow.book.title}' returned by {borrow.user.get_full_name() or borrow.user.email}!", extra_tags='green')
        print(f"Borrow ID {borrow_id} returned by {request.user.email}")
        return redirect('active_borrows_list')
    
    context = {'borrow': borrow}
    return render(request, 'borrows/borrow_receive_return.html', context)

@login_required
def all_borrows_history(request):
    """Librarian views complete borrow history"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(f"Unauthorized access to all_borrows_history by {request.user.email}")
        return redirect('book_list')
    
    # Get all borrows
    borrows = Borrow.objects.all().select_related(
        'book', 'user', 'issued_by', 'returned_to', 'centre', 'book__category'
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
            Q(book__title__icontains=search) |
            Q(book__book_code__icontains=search)
        )
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        borrows = borrows.filter(status=status)
    
    borrows = borrows.order_by('-request_date')
    
    # Pagination
    paginator = Paginator(borrows, 50)
    page_number = request.GET.get('page')
    borrows_page = paginator.get_page(page_number)
    
    context = {
        'borrows': borrows_page,
        'search': search,
        'status_filter': status,
    }
    print(f"Librarian {request.user.email} viewed all_borrows_history: {borrows.count()} borrows")
    return render(request, 'borrows/all_borrows_history.html', context)

# ==================== RESERVATION VIEWS ====================

@login_required
def reservation_cancel(request, reservation_id):
    """Cancel a reservation"""
    reservation = get_object_or_404(Reservation, pk=reservation_id, user=request.user)
    
    if reservation.status != 'pending':
        messages.error(request, "This reservation is no longer active.")
        print(f"Invalid cancel attempt by {request.user.email} for reservation ID {reservation_id} (status: {reservation.status})")
        return redirect('my_borrows')
    
    if request.method == 'POST':
        book_title = reservation.book.title
        reservation.status = 'cancelled'
        reservation.save()
        messages.success(request, f"Reservation for '{book_title}' cancelled.", extra_tags='green')
        print(f"Reservation ID {reservation_id} cancelled by {request.user.email}")
        return redirect('my_borrows')
    
    context = {'reservation': reservation}
    return render(request, 'reservations/reservation_cancel.html', context)

@login_required
def reservations_list(request):
    """Librarian views all reservations"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(f"Unauthorized access to reservations_list by {request.user.email}")
        return redirect('book_list')
    
    reservations = Reservation.objects.filter(status='pending').select_related(
        'book', 'user', 'centre', 'book__category'
    ).order_by('reservation_date')
    
    # Filter by centre for librarians
    if request.user.is_librarian:
        reservations = reservations.filter(centre=request.user.centre)
    
    context = {'reservations': reservations}
    print(f"Librarian {request.user.email} viewed reservations_list: {reservations.count()} reservations")
    return render(request, 'reservations/reservations_list.html', context)



@login_required
def reserve_book(request, book_id):
    """Allow a user to reserve a book if available or pending reservation exists."""
    book = get_object_or_404(Book, pk=book_id)
    
    # Check if the user is authorized to reserve (students or teachers)
    if not (request.user.is_student or request.user.is_teacher):
        messages.error(request, "You do not have permission to reserve books.")
        return redirect('book_list')
    
    # Check if the user already has an active reservation for this book
    existing_reservation = Reservation.objects.filter(
        user=request.user, book=book, status='pending'
    ).first()
    
    if existing_reservation:
        messages.warning(f"You already have a pending reservation for '{book.title}'.")
        return redirect('book_detail', pk=book.id)
    
    # Check if the book has available copies (suggest borrowing instead)
    if book.available_copies > 0:
        messages.info(request, f"'{book.title}' has available copies. Consider borrowing instead.")
        return redirect('book_detail', pk=book.id)
    
    if request.method == 'POST' and 'confirm_reserve' in request.POST:
        # Create a new reservation with the user's centre
        reservation = Reservation.objects.create(
            user=request.user,
            book=book,
            centre=request.user.centre,
            expiry_date=timezone.now() + timedelta(days=7),
            status='pending'
        )
        messages.success(request, f"Reservation for '{book.title}' created successfully.", extra_tags='green')
        print(f"Reservation ID {reservation.id} created by {request.user.email} for book '{book.title}'")
        return redirect('my_borrows')
    
    context = {'book': book}
    return render(request, 'reservations/reserve_book.html', context)