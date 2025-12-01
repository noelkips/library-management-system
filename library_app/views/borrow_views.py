from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
from datetime import timedelta
from django.db import transaction
from ..models import (
    Book,
    Borrow,
    Reservation,
    Notification,
    CustomUser,
    Student,
    can_user_borrow,
    get_user_borrow_limit,
    Category,
)

# ==================== USER BORROW REQUEST VIEWS ====================


def is_staff_user(user):
    """
    Returns True if user is a librarian, site admin, or superuser.
    This replaces Django's default user.is_staff
    """
    return bool(
        user.is_authenticated and (
            user.is_librarian or
            user.is_site_admin or
            user.is_superuser
        )
    )


@login_required
def borrow_request(request, book_id):
    if request.method != "POST":
        return redirect("book_detail", pk=book_id)

    if not (
        request.user.is_student
        or request.user.is_teacher
        or request.user.is_other
    ):
        messages.error(
            request,
            "Only students, teachers, and other users can borrow books.",
        )
        print(
            f"Unauthorized borrow attempt by {request.user.email} "
            f"for book ID {book_id}"
        )
        return redirect("book_detail", pk=book_id)

    book = get_object_or_404(Book, pk=book_id, is_active=True)

    # Check if user can borrow
    if not can_user_borrow(request.user):
        limit = get_user_borrow_limit(request.user)
        messages.error(
            request,
            f"You have reached your borrow limit of {limit} "
            f"book{'s' if limit != 1 else ''}.",
        )
        print(
            f"Borrow limit reached for {request.user.email} (limit: {limit})"
        )
        return redirect("book_detail", pk=book_id)

    # Check if user already has active borrow/request for this book
    existing_borrow = Borrow.objects.filter(
        book=book,
        user=request.user,
        status__in=["requested", "issued"],
    ).first()

    if existing_borrow:
        messages.warning(
            request,
            "You already have an active request or borrow for this book.",
        )
        print(
            f"Duplicate borrow attempt by {request.user.email} "
            f"for book '{book.title}'"
        )
        return redirect("book_detail", pk=book_id)

    # Check if book is available
    if book.is_available():
        # Create borrow request
        Borrow.objects.create(
            book=book,
            user=request.user,
            centre=book.centre,
            status="requested",
            notes=request.POST.get("notes", ""),
        )

        # Notify librarians
        librarians = CustomUser.objects.filter(
            is_librarian=True, centre=book.centre
        )
        for librarian in librarians:
            Notification.objects.create(
                user=librarian,
                message=(
                    f"{request.user.get_full_name() or request.user.email} "
                    f"requested to borrow '{book.title}'"
                ),
            )

        messages.success(
            request,
            f"Borrow request for '{book.title}' submitted! "
            "Wait for librarian approval.",
            extra_tags="green",
        )
        print(
            f"Borrow request created by {request.user.email} "
            f"for '{book.title}' (ID: {book_id})"
        )
    else:
        # Book not available - create reservation
        existing_reservation = Reservation.objects.filter(
            book=book, user=request.user, status="pending"
        ).first()

        if existing_reservation:
            messages.warning(
                request, "You already have a reservation for this book."
            )
            print(
                f"Duplicate reservation attempt by {request.user.email} "
                f"for '{book.title}'"
            )
        else:
            Reservation.objects.create(
                book=book,
                user=request.user,
                centre=book.centre,
            )
            messages.info(
                request,
                f"'{book.title}' is currently unavailable. "
                "You've been added to the reservation list.",
            )
            print(
                f"Reservation created by {request.user.email} "
                f"for '{book.title}'"
            )
    return redirect("book_detail", pk=book_id)

@login_required
def my_borrows(request):
    """User views their borrow history"""
    if not (
        request.user.is_student
        or request.user.is_teacher
        or request.user.is_other
    ):
        messages.error(request, "This page is for borrowers only.")
        print(
            f"Unauthorized access to my_borrows by {request.user.email}"
        )
        return redirect("book_list")

    # Get all borrows
    borrows = Borrow.objects.filter(user=request.user).select_related(
        "book", "issued_by", "returned_to", "book__category"
    ).order_by("-request_date")

    # Separate active and history
    active_borrows = borrows.filter(status__in=["requested", "issued"])
    history_borrows = borrows.filter(status="returned")[:20]

    # Get reservations
    reservations = Reservation.objects.filter(
        user=request.user, status="pending"
    ).select_related("book", "book__category")

    # Get borrow limit info
    limit = get_user_borrow_limit(request.user)
    can_borrow_more = can_user_borrow(request.user)

    context = {
        "active_borrows": active_borrows,
        "history_borrows": history_borrows,
        "reservations": reservations,
        "borrow_limit": limit,
        "can_borrow_more": can_borrow_more,
    }
    print(
        f"User {request.user.email} viewed my_borrows: "
        f"{active_borrows.count()} active, "
        f"{history_borrows.count()} history"
    )
    return render(request, "borrows/my_borrows.html", context)

@login_required
def borrow_cancel(request, borrow_id):
    """User cancels their borrow request"""
    borrow = get_object_or_404(Borrow, pk=borrow_id, user=request.user)

    if borrow.status != "requested":
        messages.error(request, "You can only cancel pending requests.")
        print(
            f"Invalid cancel attempt by {request.user.email} "
            f"for borrow ID {borrow_id} (status: {borrow.status})"
        )
        return redirect("my_borrows")

    if request.method == "POST":
        book_title = borrow.book.title
        borrow.delete()
        messages.success(
            request,
            f"Borrow request for '{book_title}' cancelled.",
            extra_tags="green",
        )
        print(
            f"Borrow request ID {borrow_id} cancelled "
            f"by {request.user.email}"
        )
        return redirect("my_borrows")

    context = {"borrow": borrow}
    return render(request, "borrows/borrow_cancel.html", context)

@login_required
def borrow_renew(request, borrow_id):
    """User requests to renew their borrow"""
    borrow = get_object_or_404(Borrow, pk=borrow_id, user=request.user)

    if borrow.status != "issued":
        messages.error(request, "You can only renew issued books.")
        print(
            f"Invalid renew attempt by {request.user.email} "
            f"for borrow ID {borrow_id} (status: {borrow.status})"
        )
        return redirect("my_borrows")

    if borrow.renew(user=request.user):
        messages.success(
            request,
            f"'{borrow.book.title}' renewed successfully! "
            f"New due date: {borrow.due_date.strftime('%Y-%m-%d')}",
            extra_tags="green",
        )
        print(
            f"Borrow ID {borrow_id} renewed by {request.user.email}, "
            f"new due date: {borrow.due_date}"
        )
    else:
        messages.error(
            request,
            "Maximum renewals reached (2). Please return the book.",
        )
        print(
            f"Max renewals reached for borrow ID {borrow_id} "
            f"by {request.user.email}"
        )

    return redirect("my_borrows")

# ==================== TEACHER-SPECIFIC VIEWS ====================

@login_required
def teacher_book_list(request):
    if not request.user.is_teacher:
        messages.error(request, "This page is for teachers only.")
        print(
            f"Unauthorized access to teacher_book_list "
            f"by {request.user.email}"
        )
        return redirect("book_list")

    # Same queryset as book_list, but filter to teacher's centre
    books = Book.objects.filter(
        centre=request.user.centre, is_active=True
    )

    # Apply filters same as book_list
    query = request.GET.get("q", "")
    category_id = request.GET.get("category", "")
    available_only = "available" in request.GET

    if query:
        books = books.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
            | Q(book_code__icontains=query)
            | Q(isbn__icontains=query)
        )
    if category_id:
        books = books.filter(category_id=category_id)
    if available_only:
        books = books.filter(available_copies=True)

    books = books.order_by("title")

    paginator = Paginator(books, 20)  # Adjust as needed
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    categories = Category.objects.all()

    context = {
        "page_obj": page_obj,
        "query": query,
        "selected_category": category_id,
        "available_only": available_only,
        "categories": categories,
    }
    print(
        f"Teacher {request.user.email} viewed teacher_book_list: "
        f"{books.count()} books"
    )
    return render(
        request, "borrows/teacher_book_list.html", context
    )

@login_required
@transaction.atomic
def bulk_borrow_request(request):
    if not request.user.is_teacher:
        messages.error(
            request, "Only teachers can make bulk borrow requests."
        )
        return redirect("teacher_book_list")

    if request.method != "POST":
        return redirect("teacher_book_list")

    book_ids = request.POST.getlist("book_ids")
    if not book_ids:
        messages.error(request, "No books selected.")
        return redirect("teacher_book_list")

    created = 0
    failed = []
    # Teachers are not limited, so no limit check

    for book_id in book_ids:
        book = get_object_or_404(
            Book,
            pk=book_id,
            is_active=True,
            centre=request.user.centre,
        )

        # Check existing
        if Borrow.objects.filter(
            book=book,
            user=request.user,
            status__in=["requested", "issued"],
        ).exists():
            failed.append(f"{book.title}: Already requested/borrowed")
            continue

        if book.is_available():
            borrow = Borrow.objects.create(
                book=book,
                user=request.user,
                centre=book.centre,
                status="requested",
                notes="",  # Optional: can add a field if needed
            )
            # Notify librarians
            librarians = CustomUser.objects.filter(
                is_librarian=True, centre=book.centre
            )
            for librarian in librarians:
                Notification.objects.create(
                    user=librarian,
                    message=(
                        f"{request.user.get_full_name() or request.user.email} "
                        f"requested to borrow '{book.title}' (bulk)"
                    ),
                )
            created += 1
        else:
            failed.append(f"{book.title}: Unavailable")

    if created:
        messages.success(
            request,
            f"{created} borrow requests created successfully.",
            extra_tags="green",
        )
    if failed:
        messages.warning(
            request, f"Failed: {'; '.join(failed)}"
        )

    print(
        f"Bulk borrow by {request.user.email}: "
        f"{created} created, {len(failed)} failed"
    )
    return redirect("my_borrows")

@login_required
@transaction.atomic
def bulk_reserve_book(request):
    if not request.user.is_teacher:
        messages.error(
            request, "Only teachers can make bulk reservations."
        )
        return redirect("teacher_book_list")

    if request.method != "POST":
        return redirect("teacher_book_list")

    book_ids = request.POST.getlist("book_ids")
    if not book_ids:
        messages.error(request, "No books selected.")
        return redirect("teacher_book_list")

    created = 0
    failed = []

    for book_id in book_ids:
        book = get_object_or_404(
            Book, pk=book_id, centre=request.user.centre
        )

        # Check existing reservation
        if Reservation.objects.filter(
            user=request.user, book=book, status="pending"
        ).exists():
            failed.append(f"{book.title}: Already reserved")
            continue

        if book.available_copies:
            failed.append(f"{book.title}: Available - borrow instead")
            continue

        Reservation.objects.create(
            user=request.user,
            book=book,
            centre=request.user.centre,
            expiry_date=timezone.now() + timedelta(days=7),
            status="pending",
        )
        created += 1

    if created:
        messages.success(
            request,
            f"{created} reservations created successfully.",
            extra_tags="green",
        )
    if failed:
        messages.warning(
            request, f"Failed: {'; '.join(failed)}"
        )

    print(
        f"Bulk reserve by {request.user.email}: "
        f"{created} created, {len(failed)} failed"
    )
    return redirect("my_borrows")

@login_required
def borrow_add(request):
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to add borrows.")
        print(
            f"Unauthorized borrow add attempt by {request.user.email}"
        )
        return redirect("book_list")

    if request.method == 'POST':
        student_id = request.POST.get('student')
        book_id = request.POST.get('book')
        try:
            student = Student.objects.get(id=student_id)
            book = Book.objects.get(id=book_id)
            if book.is_available():
                if not can_user_borrow(student.user):
                    messages.error(
                        request,
                        f"{student.name} has reached their borrowing limit."
                    )
                    print(
                        f"Borrow limit reached for {student.user.email} "
                        f"when adding borrow by {request.user.email}"
                    )
                    return redirect("borrow_add")
                borrow = Borrow.objects.create(
                    user=student.user,
                    book=book,
                    centre=book.centre,
                    status="issued",
                    issue_date=timezone.now(),
                    due_date=timezone.now() + timedelta(days=7),
                    issued_by=request.user,
                )
                book.update_available_copies()
                Notification.objects.create(
                    user=student.user,
                    message=(
                        f"Your borrow request for '{book.title}' has been "
                        f"approved! Due: {borrow.due_date.strftime('%Y-%m-%d')}"
                    ),
                    book=book,
                    borrow=borrow,
                    notification_type="borrow_approved",
                )
                messages.success(request, 'Book borrowed successfully!', extra_tags="green")
                print(
                    f"Borrow created for {student.user.email} "
                    f"for book '{book.title}' by {request.user.email}"
                )
                return redirect('borrow_requests_list')
            else:
                messages.error(request, 'Book is not available.')
                print(
                    f"Book '{book.title}' not available for borrow "
                    f"by {request.user.email}"
                )
        except (Student.DoesNotExist, Book.DoesNotExist):
            messages.error(request, 'Invalid student or book.')
            print(f"Invalid student ID {student_id} or book ID {book_id}")
    students = Student.objects.all()
    books = Book.objects.filter(available_copies=True)
    return render(request, 'borrow/borrow_add.html', {'students': students, 'books': books})

# ==================== LIBRARIAN BORROW MANAGEMENT VIEWS ====================

@login_required
def borrow_requests_list(request):
    """Librarian views pending borrow requests grouped by user"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(
            f"Unauthorized access to borrow_requests_list "
            f"by {request.user.email}"
        )
        return redirect("book_list")

    # Get all users who have pending borrow requests
    users_query = CustomUser.objects.filter(
        borrows__status="requested"
    ).annotate(
        pending_count=Count('borrows', filter=Q(borrows__status='requested'))
    ).select_related('centre').distinct()

    # Filter by centre for librarians (not site admins)
    if request.user.is_librarian and not request.user.is_site_admin:
        users_query = users_query.filter(centre=request.user.centre)

    # Search functionality
    search = request.GET.get("search", "")
    if search:
        users_query = users_query.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
        )

    # Order by number of pending requests (descending)
    users_query = users_query.order_by('-pending_count')

    # Pagination
    paginator = Paginator(users_query, 20)
    page_number = request.GET.get("page")
    users_with_requests = paginator.get_page(page_number)

    context = {
        "users_with_requests": users_with_requests,
        "search": search,
    }
    
    print(
        f"Librarian {request.user.email} viewed borrow_requests_list: "
        f"{users_query.count()} users with pending requests"
    )
    return render(request, "borrows/borrow_requests_list.html", context)

@login_required
def borrow_issue(request, borrow_id):
    """Librarian issues a book (approves borrow request)"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to issue books.")
        print(
            f"Unauthorized issue attempt by {request.user.email} "
            f"for borrow ID {borrow_id}"
        )
        return redirect("book_list")

    borrow = get_object_or_404(Borrow, pk=borrow_id)

    # Check permissions
    if request.user.is_librarian and borrow.centre != request.user.centre:
        messages.error(
            request, "You can only issue books from your centre."
        )
        print(
            f"Unauthorized issue attempt by {request.user.email} "
            f"for borrow ID {borrow_id} (wrong centre)"
        )
        return redirect("borrow_requests_list")

    if borrow.status != "requested":
        messages.error(
            request, "This borrow request has already been processed."
        )
        print(
            f"Invalid issue attempt by {request.user.email} "
            f"for borrow ID {borrow_id} (status: {borrow.status})"
        )
        return redirect("borrow_requests_list")

    # Check if book is still available
    if not borrow.book.is_available():
        messages.error(
            request, f"'{borrow.book.title}' is no longer available."
        )
        print(
            f"Book '{borrow.book.title}' unavailable "
            f"for borrow ID {borrow_id}"
        )
        return redirect("borrow_requests_list")

    if request.method == "POST":
        try:
            # Get custom due date or default to 3 days
            days = int(request.POST.get("days", 3))
            if days <= 0 or days > 30:
                messages.error(
                    request, "Due date must be between 1 and 30 days."
                )
                print(
                    f"Invalid days ({days}) for borrow ID {borrow_id} "
                    f"by {request.user.email}"
                )
                return redirect("borrow_issue", borrow_id=borrow_id)

            due_date = timezone.now() + timedelta(days=days)
            if due_date.year > 2025:
                messages.error(
                    request, "Due date cannot be set beyond 2025."
                )
                print(
                    f"Due date beyond 2025 for borrow ID {borrow_id} "
                    f"by {request.user.email}"
                )
                return redirect("borrow_issue", borrow_id=borrow_id)

            # Issue the book
            borrow.status = "issued"
            borrow.issue_date = timezone.now()
            borrow.due_date = due_date
            borrow.issued_by = request.user
            borrow.save(user=request.user)

            # Update book availability
            borrow.book.update_available_copies()

            # Notify user
            Notification.objects.create(
                user=borrow.user,
                message=(
                    f"Your request for '{borrow.book.title}' has been "
                    f"approved! Due date: "
                    f"{borrow.due_date.strftime('%Y-%m-%d')}"
                ),
                book=borrow.book,
                borrow=borrow,
                notification_type="borrow_approved",
            )

            messages.success(
                request,
                f"Book '{borrow.book.title}' issued to "
                f"{borrow.user.get_full_name() or borrow.user.email}!",
                extra_tags="green",
            )
            print(
                f"Borrow ID {borrow_id} issued by {request.user.email} "
                f"to {borrow.user.email}"
            )
            return redirect("borrow_requests_list")
        except ValueError:
            messages.error(request, "Invalid number of days provided.")
            print(
                f"ValueError: Invalid days input for borrow ID {borrow_id} "
                f"by {request.user.email}"
            )

    context = {"borrow": borrow}
    return render(request, "borrows/borrow_issue.html", context)

@login_required
def borrow_reject(request, borrow_id):
    """Librarian rejects a borrow request"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(
            request, "You don't have permission to reject requests."
        )
        print(
            f"Unauthorized reject attempt by {request.user.email} "
            f"for borrow ID {borrow_id}"
        )
        return redirect("book_list")

    borrow = get_object_or_404(Borrow, pk=borrow_id)

    # Check permissions
    if request.user.is_librarian and borrow.centre != request.user.centre:
        messages.error(
            request, "You can only manage requests from your centre."
        )
        print(
            f"Unauthorized reject attempt by {request.user.email} "
            f"for borrow ID {borrow_id} (wrong centre)"
        )
        return redirect("borrow_requests_list")

    if borrow.status != "requested":
        messages.error(
            request, "This borrow request has already been processed."
        )
        print(
            f"Invalid reject attempt by {request.user.email} "
            f"for borrow ID {borrow_id} (status: {borrow.status})"
        )
        return redirect("borrow_requests_list")

    if request.method == "POST":
        reason = request.POST.get("reason", "No reason provided")

        # Notify user
        Notification.objects.create(
            user=borrow.user,
            message=(
                f"Your request for '{borrow.book.title}' was rejected. "
                f"Reason: {reason}"
            ),
            book=borrow.book,
            borrow=borrow,
            notification_type="borrow_rejected",
        )

        # Delete the request
        book_title = borrow.book.title
        user_name = borrow.user.get_full_name() or borrow.user.email
        borrow.delete()

        messages.success(
            request,
            f"Borrow request for '{book_title}' by {user_name} rejected.",
            extra_tags="green",
        )
        print(
            f"Borrow ID {borrow_id} rejected by {request.user.email}, "
            f"reason: {reason}"
        )
        return redirect("borrow_requests_list")

    context = {"borrow": borrow}
    return render(request, "borrows/borrow_reject.html", context)

@login_required
def active_borrows_list(request):
    """Librarian views all active borrows (issued books)"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(
            f"Unauthorized access to active_borrows_list "
            f"by {request.user.email}"
        )
        return redirect("book_list")

    user_type = request.GET.get("user_type", "students")
    centre_filter = Q(centre=request.user.centre) if request.user.is_librarian else Q()
    search = request.GET.get("search", "")
    status_filter = request.GET.get("status", "")

    if user_type == "teachers":
        # List of teachers with active borrows
        users_query = CustomUser.objects.filter(
            is_teacher=True,
            borrows__status="issued"
        ).annotate(
            active_count=Count("borrows", filter=Q(borrows__status="issued"))
        ).filter(centre_filter).distinct()

        if search:
            users_query = users_query.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        if status_filter == "overdue":
            users_query = users_query.filter(
                borrows__status="issued",
                borrows__due_date__lt=timezone.now()
            ).distinct()

        users_query = users_query.order_by("-active_count")

        paginator = Paginator(users_query, 20)
        page_number = request.GET.get("page")
        users_with_active = paginator.get_page(page_number)

        context = {
            "users_with_active": users_with_active,
            "search": search,
            "status_filter": status_filter,
            "user_type": user_type,
        }
        print(
            f"Librarian {request.user.email} viewed active_borrows_list (teachers): "
            f"{users_query.count()} teachers with active borrows"
        )
        return render(request, "borrows/active_borrows_users.html", context)
    else:
        # Direct list for students
        borrows = Borrow.objects.filter(
            status="issued",
            user__is_student=True
        ).filter(centre_filter).select_related(
            "book", "user", "issued_by", "centre", "book__category"
        )

        if search:
            borrows = borrows.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(book__title__icontains=search)
                | Q(book__book_code__icontains=search)
            )

        if status_filter == "overdue":
            borrows = borrows.filter(due_date__lt=timezone.now())

        borrows = borrows.order_by("due_date")

        paginator = Paginator(borrows, 20)
        page_number = request.GET.get("page")
        borrows_page = paginator.get_page(page_number)

        context = {
            "borrows": borrows_page,
            "search": search,
            "status_filter": status_filter,
            "user_type": user_type,
        }
        print(
            f"Librarian {request.user.email} viewed active_borrows_list (students): "
            f"{borrows.count()} borrows"
        )
        return render(request, "borrows/active_borrows_list.html", context)

@login_required
def borrow_receive_return(request, borrow_id):
    """Librarian receives a returned book"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(
            request, "You don't have permission to receive returns."
        )
        print(
            f"Unauthorized return attempt by {request.user.email} "
            f"for borrow ID {borrow_id}"
        )
        return redirect("book_list")

    borrow = get_object_or_404(Borrow, pk=borrow_id)

    # Check permissions
    if request.user.is_librarian and borrow.centre != request.user.centre:
        messages.error(
            request, "You can only receive returns for your centre."
        )
        print(
            f"Unauthorized return attempt by {request.user.email} "
            f"for borrow ID {borrow_id} (wrong centre)"
        )
        return redirect("active_borrows_list")

    if borrow.status != "issued":
        messages.error(request, "This book is not currently issued.")
        print(
            f"Invalid return attempt by {request.user.email} "
            f"for borrow ID {borrow_id} (status: {borrow.status})"
        )
        return redirect("active_borrows_list")

    if request.method == "POST":
        # Mark as returned
        borrow.status = "returned"
        borrow.return_date = timezone.now()
        borrow.returned_to = request.user
        borrow.save(user=request.user)

        # Update book availability
        borrow.book.update_available_copies()

        # Check for pending reservations
        pending_reservation = Reservation.objects.filter(
            book=borrow.book, status="pending"
        ).order_by("reservation_date").first()

        if pending_reservation:
            # Notify user with reservation
            Notification.objects.create(
                user=pending_reservation.user,
                message=(
                    f"'{borrow.book.title}' is now available! Your "
                    "reservation is ready. Please request to borrow "
                    "within 2 days."
                ),
                book=borrow.book,
                reservation=pending_reservation,
                notification_type="book_available",
            )
            pending_reservation.notified = True
            pending_reservation.save()

        # Notify user
        Notification.objects.create(
            user=borrow.user,
            message=f"Thank you for returning '{borrow.book.title}'!",
            book=borrow.book,
            borrow=borrow,
            notification_type="book_returned",
        )

        messages.success(
            request,
            f"Book '{borrow.book.title}' returned by "
            f"{borrow.user.get_full_name() or borrow.user.email}!",
            extra_tags="green",
        )
        print(f"Borrow ID {borrow_id} returned by {request.user.email}")
        return redirect("active_borrows_list")

    context = {"borrow": borrow}
    return render(request, "borrows/borrow_receive_return.html", context)

@login_required
def all_borrows_history(request):
    """Librarian views complete borrow history"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(
            f"Unauthorized access to all_borrows_history "
            f"by {request.user.email}"
        )
        return redirect("book_list")

    user_type = request.GET.get("user_type", "students")
    centre_filter = Q(centre=request.user.centre) if request.user.is_librarian else Q()
    search = request.GET.get("search", "")
    status = request.GET.get("status", "")

    if user_type == "teachers":
        # List of teachers with borrow history
        users_query = CustomUser.objects.filter(
            is_teacher=True,
            borrows__isnull=False
        ).annotate(
            history_count=Count("borrows")
        ).filter(centre_filter).distinct()

        if search:
            users_query = users_query.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        if status:
            users_query = users_query.filter(borrows__status=status).distinct()

        users_query = users_query.order_by("-history_count")

        paginator = Paginator(users_query, 20)
        page_number = request.GET.get("page")
        users_with_history = paginator.get_page(page_number)

        context = {
            "users_with_history": users_with_history,
            "search": search,
            "status_filter": status,
            "user_type": user_type,
        }
        print(
            f"Librarian {request.user.email} viewed all_borrows_history (teachers): "
            f"{users_query.count()} teachers with history"
        )
        return render(request, "borrows/history_borrows_users.html", context)
    else:
        # Direct list for students
        borrows = Borrow.objects.filter(
            user__is_student=True
        ).filter(centre_filter).select_related(
            "book",
            "user",
            "issued_by",
            "returned_to",
            "centre",
            "book__category",
        )

        if search:
            borrows = borrows.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(book__title__icontains=search)
                | Q(book__book_code__icontains=search)
            )

        if status:
            borrows = borrows.filter(status=status)

        borrows = borrows.order_by("-request_date")

        paginator = Paginator(borrows, 50)
        page_number = request.GET.get("page")
        borrows_page = paginator.get_page(page_number)

        context = {
            "borrows": borrows_page,
            "search": search,
            "status_filter": status,
            "user_type": user_type,
        }
        print(
            f"Librarian {request.user.email} viewed all_borrows_history (students): "
            f"{borrows.count()} borrows"
        )
        return render(request, "borrows/all_borrows_history.html", context)

# ==================== RESERVATION MANAGEMENT VIEWS ====================

@login_required
def reservation_cancel(request, reservation_id):
    """Cancel a reservation"""
    reservation = get_object_or_404(
        Reservation, pk=reservation_id, user=request.user
    )

    if reservation.status != "pending":
        messages.error(request, "This reservation is no longer active.")
        print(
            f"Invalid cancel attempt by {request.user.email} "
            f"for reservation ID {reservation_id} "
            f"(status: {reservation.status})"
        )
        return redirect("my_borrows")

    if request.method == "POST":
        book_title = reservation.book.title
        reservation.status = "cancelled"
        reservation.save()
        messages.success(
            request,
            f"Reservation for '{book_title}' cancelled.",
            extra_tags="green",
        )
        print(
            f"Reservation ID {reservation_id} cancelled "
            f"by {request.user.email}"
        )
        return redirect("my_borrows")

    context = {"reservation": reservation}
    return render(request, "reservations/reservation_cancel.html", context)

@login_required
def reservations_list(request):
    """Librarian views all reservations"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(
            f"Unauthorized access to reservations_list "
            f"by {request.user.email}"
        )
        return redirect("book_list")

    user_type = request.GET.get("user_type", "students")
    centre_filter = Q(centre=request.user.centre) if request.user.is_librarian else Q()
    search = request.GET.get("search", "")

    if user_type == "teachers":
        # List of teachers with pending reservations
        users_query = CustomUser.objects.filter(
            is_teacher=True,
            reservations__status="pending"
        ).annotate(
            reservation_count=Count("reservations", filter=Q(reservations__status="pending"))
        ).filter(centre_filter).distinct()

        if search:
            users_query = users_query.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        users_query = users_query.order_by("-reservation_count")

        paginator = Paginator(users_query, 20)
        page_number = request.GET.get("page")
        users_with_reservations = paginator.get_page(page_number)

        context = {
            "users_with_reservations": users_with_reservations,
            "search": search,
            "user_type": user_type,
        }
        print(
            f"Librarian {request.user.email} viewed reservations_list (teachers): "
            f"{users_query.count()} teachers with reservations"
        )
        return render(request, "reservations/reservations_users.html", context)
    else:
        # Direct list for students
        reservations = Reservation.objects.filter(
            status="pending",
            user__is_student=True
        ).filter(centre_filter).select_related(
            "book", "user", "centre", "book__category"
        ).order_by("reservation_date")

        if search:
            reservations = reservations.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(book__title__icontains=search)
            )

        paginator = Paginator(reservations, 20)
        page_number = request.GET.get("page")
        reservations_page = paginator.get_page(page_number)

        context = {
            "reservations": reservations_page,
            "search": search,
            "user_type": user_type,
        }
        print(
            f"Librarian {request.user.email} viewed reservations_list (students): "
            f"{reservations.count()} reservations"
        )
        return render(request, "reservations/reservations_list.html", context)

@login_required
def reserve_book(request, book_id):
    book = get_object_or_404(Book, pk=book_id)

    if request.method != "POST":
        return redirect("book_detail", pk=book_id)

    # Check if the user is authorized to reserve (students or teachers)
    if not (request.user.is_student or request.user.is_teacher):
        messages.error(
            request, "You do not have permission to reserve books."
        )
        return redirect("book_detail", pk=book_id)

    # Check if the user already has an active reservation for this book
    existing_reservation = Reservation.objects.filter(
        user=request.user, book=book, status="pending"
    ).first()

    if existing_reservation:
        messages.warning(
            request,
            f"You already have a pending reservation for '{book.title}'.",
        )
        return redirect("book_detail", pk=book_id)

    # Check if the book has available copies (suggest borrowing instead)
    if book.available_copies:
        messages.info(
            request,
            f"'{book.title}' is available. Consider borrowing instead.",
        )
        return redirect("book_detail", pk=book_id)

    # Create a new reservation with the user's centre
    reservation = Reservation.objects.create(
        user=request.user,
        book=book,
        centre=request.user.centre,
        expiry_date=timezone.now() + timedelta(days=7),
        status="pending",
    )
    messages.success(
        request,
        f"Reservation for '{book.title}' created successfully.",
        extra_tags="green",
    )
    print(
        f"Reservation ID {reservation.id} created by {request.user.email} "
        f"for book '{book.title}'"
    )
    return redirect("book_detail", pk=book_id)

# ==================== ADMIN/LIBRARIAN USER MANAGEMENT VIEWS ====================

@login_required
def user_borrow_details(request, user_id):
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        return redirect("borrow_requests_list")

    borrow_user = get_object_or_404(CustomUser, pk=user_id)

    # Check centre permission
    if request.user.is_librarian and borrow_user.centre != request.user.centre:
        messages.error(request, "You can only manage users from your centre.")
        return redirect("borrow_requests_list")

    pending_borrows = Borrow.objects.filter(
        user=borrow_user, status="requested"
    ).select_related("book")

    context = {
        "user": borrow_user,
        "pending_borrows": pending_borrows,
    }
    print(
        f"Librarian {request.user.email} viewed borrow details for user "
        f"{borrow_user.email}: {pending_borrows.count()} pending"
    )
    return render(request, "borrows/user_borrow_details.html", context)

@login_required
@transaction.atomic
def bulk_issue_borrows(request, user_id):
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to issue books.")
        return redirect("borrow_requests_list")

    if request.method != "POST":
        return redirect("user_borrow_details", user_id=user_id)

    borrow_ids = request.POST.getlist("borrow_ids")
    if not borrow_ids:
        messages.error(request, "No requests selected.")
        return redirect("user_borrow_details", user_id=user_id)

    try:
        days = int(request.POST.get("days", 3))
        if days < 1 or days > 30:
            raise ValueError("Days must be 1-30")
        due_date = timezone.now() + timedelta(days=days)
        if due_date.year > 2025:
            raise ValueError("Due date beyond 2025")
    except ValueError as e:
        messages.error(request, f"Invalid due date: {str(e)}")
        return redirect("user_borrow_details", user_id=user_id)

    issued = 0
    failed = []
    borrows = Borrow.objects.filter(id__in=borrow_ids, status="requested")

    for borrow in borrows:
        if not borrow.book.is_available():
            failed.append(f"{borrow.book.title}: Unavailable")
            continue

        borrow.status = "issued"
        borrow.issue_date = timezone.now()
        borrow.due_date = due_date
        borrow.issued_by = request.user
        borrow.save(user=request.user)

        borrow.book.update_available_copies()

        Notification.objects.create(
            user=borrow.user,
            message=(
                f"Your request for '{borrow.book.title}' has been approved! "
                f"Due: {due_date.strftime('%Y-%m-%d')}"
            ),
            book=borrow.book,
            borrow=borrow,
            notification_type="borrow_approved",
        )
        issued += 1

    if issued:
        messages.success(
            request,
            f"{issued} requests issued successfully.",
            extra_tags="green",
        )
    if failed:
        messages.warning(request, f"Failed: {'; '.join(failed)}")

    print(
        f"Bulk issue by {request.user.email} for user {user_id}: "
        f"{issued} issued, {len(failed)} failed"
    )
    return redirect("user_borrow_details", user_id=user_id)

@login_required
@transaction.atomic
def bulk_reject_borrows(request, user_id):
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(
            request, "You don't have permission to reject requests."
        )
        return redirect("borrow_requests_list")

    if request.method != "POST":
        return redirect("user_borrow_details", user_id=user_id)

    borrow_ids = request.POST.getlist("borrow_ids")
    if not borrow_ids:
        messages.error(request, "No requests selected.")
        return redirect("user_borrow_details", user_id=user_id)

    rejected = 0
    borrows = Borrow.objects.filter(id__in=borrow_ids, status="requested")

    for borrow in borrows:
        Notification.objects.create(
            user=borrow.user,
            message=(
                f"Your request for '{borrow.book.title}' was rejected. "
                "Contact librarian for details."
            ),
            book=borrow.book,
            borrow=borrow,
            notification_type="borrow_rejected",
        )
        borrow.delete()
        rejected += 1

    if rejected:
        messages.success(
            request,
            f"{rejected} requests rejected.",
            extra_tags="green",
        )

    print(
        f"Bulk reject by {request.user.email} for user {user_id}: "
        f"{rejected} rejected"
    )
    return redirect("user_borrow_details", user_id=user_id)

# ==================== GROUPED MANAGEMENT DETAIL VIEWS ====================

@login_required
def user_active_borrows(request, user_id):
    """Librarian views a user's active borrows"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(
            f"Unauthorized access to user_active_borrows "
            f"by {request.user.email}"
        )
        return redirect("active_borrows_list")

    borrow_user = get_object_or_404(CustomUser, pk=user_id)

    # Check centre permission
    if request.user.is_librarian and borrow_user.centre != request.user.centre:
        messages.error(request, "You can only manage users from your centre.")
        return redirect("active_borrows_list")

    active_borrows = Borrow.objects.filter(
        user=borrow_user, status="issued"
    ).select_related("book", "issued_by", "centre", "book__category").order_by("due_date")

    paginator = Paginator(active_borrows, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "user": borrow_user,
        "active_borrows": page_obj,
    }
    print(
        f"Librarian {request.user.email} viewed active borrows for user "
        f"{borrow_user.email}: {active_borrows.count()} active"
    )
    return render(request, "borrows/user_active_borrows.html", context)

@login_required
def user_history_borrows(request, user_id):
    """Librarian views a user's borrow history"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(
            f"Unauthorized access to user_history_borrows "
            f"by {request.user.email}"
        )
        return redirect("all_borrows_history")

    borrow_user = get_object_or_404(CustomUser, pk=user_id)

    # Check centre permission
    if request.user.is_librarian and borrow_user.centre != request.user.centre:
        messages.error(request, "You can only manage users from your centre.")
        return redirect("all_borrows_history")

    history_borrows = Borrow.objects.filter(
        user=borrow_user
    ).select_related(
        "book", "issued_by", "returned_to", "centre", "book__category"
    ).order_by("-request_date")

    paginator = Paginator(history_borrows, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "user": borrow_user,
        "history_borrows": page_obj,
    }
    print(
        f"Librarian {request.user.email} viewed history for user "
        f"{borrow_user.email}: {history_borrows.count()} borrows"
    )
    return render(request, "borrows/user_history_borrows.html", context)

@login_required
def user_reservations(request, user_id):
    """Librarian views a user's reservations"""
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to view this page.")
        print(
            f"Unauthorized access to user_reservations "
            f"by {request.user.email}"
        )
        return redirect("reservations_list")

    borrow_user = get_object_or_404(CustomUser, pk=user_id)

    # Check centre permission
    if request.user.is_librarian and borrow_user.centre != request.user.centre:
        messages.error(request, "You can only manage users from your centre.")
        return redirect("reservations_list")

    reservations = Reservation.objects.filter(
        user=borrow_user, status="pending"
    ).select_related("book", "centre", "book__category").order_by("reservation_date")

    paginator = Paginator(reservations, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "user": borrow_user,
        "reservations": page_obj,
    }
    print(
        f"Librarian {request.user.email} viewed reservations for user "
        f"{borrow_user.email}: {reservations.count()} reservations"
    )
    return render(request, "reservations/user_reservations.html", context)



# ==================== NEW LIBRARIAN DIRECT ISSUE VIEW ====================
@login_required
@transaction.atomic
def librarian_issue_book(request):
    """
    Librarian/Admin selects a student and an available book, and issues it.
    This atomically creates the 'requested' and 'issued' borrow steps.
    Notifies both the student and the issuing admin.
    """
    if not (request.user.is_librarian or request.user.is_site_admin):
        messages.error(request, "You don't have permission to perform this action.")
        print(f"Unauthorized access to librarian_issue_book by {request.user.email}")
        return redirect("book_list")

    if request.method == "POST":
        student_id = request.POST.get("student")
        book_id = request.POST.get("book")
        days_str = request.POST.get("days", "3")

        try:
            student = Student.objects.select_related('user', 'centre').get(id=student_id)
            book = Book.objects.get(id=book_id)
            
            if not student.user:
                 messages.error(request, f"Student {student.name} does not have an associated user account.")
                 print(f"Librarian issue failed: Student ID {student.id} has no user account.")
                 return redirect("librarian_issue_book")
                 
            user = student.user

            # Check permissions
            if request.user.is_librarian and not request.user.is_site_admin:
                if book.centre != request.user.centre or student.centre != request.user.centre:
                    messages.error(request, "You can only issue books to students in your own centre.")
                    print(f"Librarian issue failed: {request.user.email} (Centre {request.user.centre.id}) "
                          f"tried to issue to student {student.id} (Centre {student.centre.id}) "
                          f"or book {book.id} (Centre {book.centre.id})")
                    return redirect("librarian_issue_book")
            
            # Validate days
            try:
                days = int(days_str)
                if days <= 0 or days > 30:
                    raise ValueError("Days must be between 1 and 30.")
                due_date = timezone.now() + timedelta(days=days)
                if due_date.year > 2025:
                    raise ValueError("Due date cannot be set beyond 2025.")
            except (ValueError, TypeError):
                messages.error(request, "Invalid borrow duration. Must be a number between 1 and 30, and not exceed 2025.")
                print(f"Librarian issue failed: Invalid days '{days_str}' by {request.user.email}")
                return redirect("librarian_issue_book")

            # Check borrow limit
            if not can_user_borrow(user):
                limit = get_user_borrow_limit(user)
                messages.error(request, f"Student {student.name} has reached their borrow limit of {limit} book(s).")
                print(f"Librarian issue failed: Borrow limit reached for {user.email}")
                return redirect("librarian_issue_book")

            # Check book availability
            if not book.is_available():
                messages.error(request, f"Book '{book.title}' is no longer available.")
                print(f"Librarian issue failed: Book {book.id} not available")
                return redirect("librarian_issue_book")

            # Check if user already has active borrow/request for this book
            existing_borrow = Borrow.objects.filter(
                book=book,
                user=user,
                status__in=["requested", "issued"],
            ).first()
            
            if existing_borrow:
                messages.warning(request, f"Student {student.name} already has an active request or borrow for this book.")
                print(f"Librarian issue failed: Duplicate borrow for {user.email}, book {book.id}")
                return redirect("librarian_issue_book")

            # --- Atomic Request + Issue ---
            request_time = timezone.now()
            
            # 1. Create the 'requested' record
            borrow = Borrow.objects.create(
                book=book,
                user=user,
                centre=book.centre,
                status="requested",
                request_date=request_time,
                notes=f"Issued directly by librarian {request.user.email}",
            )
            
            # 2. Immediately update to 'issued'
            borrow.status = "issued"
            borrow.issue_date = request_time # Use same timestamp
            borrow.due_date = due_date
            borrow.issued_by = request.user
            borrow.save(user=request.user) # Pass user for history tracking
            
            # 3. Update book availability
            book.update_available_copies()

            # 4. Notify the student
            Notification.objects.create(
                user=user,
                message=(
                    f"A book, '{book.title}', has been issued to you by a librarian. "
                    f"Due date: {borrow.due_date.strftime('%Y-%m-%d')}"
                ),
                book=book,
                borrow=borrow,
                notification_type="borrow_approved", # Using this type for consistency
            )
            
            # --- NEW NOTIFICATION FOR ADMIN ---
            # 5. Notify the issuing librarian/admin
            Notification.objects.create(
                user=request.user, # This is the admin/librarian
                message=(
                    f"You successfully issued '{book.title}' to {student.name}. "
                    f"Due date: {borrow.due_date.strftime('%Y-%m-%d')}"
                ),
                book=book,
                borrow=borrow,
                notification_type="info", # Using 'info' as it's a confirmation
            )
            # --- END OF NEW CODE ---
            
            messages.success(request, f"Book '{book.title}' issued successfully to {student.name}!", extra_tags="green")
            print(f"Librarian issue success: {request.user.email} issued book {book.id} to {user.email}")
            return redirect("active_borrows_list")

        except Student.DoesNotExist:
            messages.error(request, "Invalid student selected.")
            print(f"Librarian issue failed: Student ID {student_id} not found.")
        except Book.DoesNotExist:
            messages.error(request, "Invalid book selected.")
            print(f"Librarian issue failed: Book ID {book_id} not found.")
        except Exception as e:
            messages.error(request, f"An unexpected error occurred: {e}")
            print(f"Librarian issue failed: Unexpected error: {e}")

    # GET request: Prepare the form
    students = Student.objects.select_related('user', 'centre').filter(user__isnull=False).order_by('name')
    books = Book.objects.filter(available_copies=True).order_by('title')

    if request.user.is_librarian and not request.user.is_site_admin:
        students = students.filter(centre=request.user.centre)
        books = books.filter(centre=request.user.centre)
        
    context = {
        "students": students,
        "books": books,
    }
    return render(request, "borrows/librarian_issue_book.html", context)



@login_required
def book_borrow_history(request, book_id):
    if not is_staff_user(request.user):
        messages.error(request, "Access denied - staff only.")
        print(f"Unauthorized access to book_borrow_history by {request.user.email} for book {book_id}")
        return redirect('book_detail', pk=book_id)

    book = get_object_or_404(Book, pk=book_id)

    # Permission check for librarian
    if request.user.is_librarian and book.centre != request.user.centre:
        messages.error(request, "Access denied to this book.")
        print(f"Unauthorized centre access by {request.user.email} for book {book_id}")
        return redirect('book_detail', pk=book_id)

    # Get all borrows for this book
    borrows = Borrow.objects.filter(book=book).select_related(
        'user', 'issued_by', 'returned_to'
    ).order_by('-request_date')

    # Paginate
    paginator = Paginator(borrows, 20)  # 20 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'book': book,
        'page_obj': page_obj,
    }
    return render(request, 'borrows/book_borrow_history.html', context)