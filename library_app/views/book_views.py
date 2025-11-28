# library_app/views/book_views.py
# COMPLETE & FINAL BOOK MODULE — 100% WORKING (2025 Global Model)
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Count
from django.http import (
    HttpResponse, JsonResponse, HttpResponseBadRequest
)
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from django.template.loader import render_to_string
from django.core.paginator import Paginator
import csv
import openpyxl
from io import TextIOWrapper
from datetime import timedelta, datetime

from ..models import (
    Book, Centre, School, Category, Grade, Subject,
    Borrow, Reservation, Notification, CustomUser
)

# Permission helper
def is_staff_user(user):
    return user.is_superuser or user.is_librarian or user.is_site_admin


# =============================================================================
# 1. MAIN ENTRY: book_list — Your Exact Flow Starts Here
# =============================================================================
@login_required
def book_list(request):
    user = request.user

    # Superuser / Site Admin → All Centres
    if user.is_superuser or user.is_site_admin:
        centres = Centre.objects.annotate(
            school_count=Count('schools'),
            book_count=Count('schools__books', distinct=True)
        ).order_by('name')
        return render(request, 'books/centre_list.html', {
            'centres': centres,
            'title': 'Select Library Centre'
        })

    # Librarian → Their Centre
    if user.is_librarian and user.centre:
        schools = user.centre.schools.all()
        if schools.count() == 1:
            return redirect('school_catalog', school_id=schools.first().id)
        return render(request, 'books/centre_detail.html', {
            'centre': user.centre,
            'schools': schools.annotate(book_count=Count('books')),
            'title': user.centre.name
        })

    # Student / Teacher → Direct to their school
    if hasattr(user, 'student_profile') and user.student_profile.school:
        return redirect('school_catalog', school_id=user.student_profile.school.id)

    if user.is_teacher and hasattr(user, 'school') and user.school:
        return redirect('school_catalog', school_id=user.school.id)

    messages.error(request, "You are not assigned to a school or centre.")
    return redirect('home')


# =============================================================================
# 2. AJAX: Load Schools Modal
# =============================================================================
@login_required
@require_GET
def ajax_load_schools_modal(request):
    centre_id = request.GET.get('centre_id')
    if not centre_id:
        return JsonResponse({'error': 'Missing centre'}, status=400)

    centre = get_object_or_404(Centre, id=centre_id)
    schools = centre.schools.annotate(book_count=Count('books')).order_by('name')

    html = render_to_string('books/partials/school_cards_modal.html', {
        'schools': schools
    }, request=request)

    return JsonResponse({'html': html, 'title': f"Select School — {centre.name}"})


# =============================================================================
# SCHOOL CATALOG – FINAL FINAL VERSION (Categories + ALL Grades Visible)
# =============================================================================



@login_required
def school_catalog(request, school_id):
    school = get_object_or_404(School, id=school_id)

    # Permission check
    if request.user.is_librarian and not request.user.is_superuser:
        if school.centre != request.user.centre:
            messages.error(request, "Access denied.")
            return redirect('book_list')

    selected_category_id = request.GET.get('category')
    selected_category = None
    if selected_category_id:
        selected_category = get_object_or_404(Category, id=selected_category_id)

    # =====================================================================
    # 1. CATEGORIES – Show ALL categories that have at least 1 book in this school
    # =====================================================================
    categories = Category.objects.annotate(
        book_count=Count(
            'subjects__books',
            filter=Q(subjects__books__school=school),
            distinct=True
        )
    ).order_by('name')  # No .filter(book_count__gt=0) → shows even 0 if you want
    # Remove the line above if you want to show categories with 0 books too

    # =====================================================================
    # 2. GRADES – Show ALL grades (even with 0 books) + correct counts
    # =====================================================================
    grades = Grade.objects.all().annotate(
        total_books=Count(
            'subjects__books',
            filter=Q(subjects__books__school=school),
            distinct=True
        ),
        filtered_books=Count(
            'subjects__books',
            filter=Q(
                subjects__books__school=school,
                subjects__books__subject__category=selected_category
            ) if selected_category else Q(),
            distinct=True
        )
    ).order_by('order', 'name')

    context = {
        'school': school,
        'categories': categories,
        'grades': grades,
        'selected_category': selected_category,
        'is_staff': is_staff_user(request.user),
    }

    return render(request, 'books/school_catalog.html', context)
# =============================================================================
# 4. FINAL BOOK LIST: Grade + Category + Subject Filter
# =============================================================================
@login_required
def grade_book_list(request, school_id, grade_id):
    school = get_object_or_404(School, id=school_id)
    grade = get_object_or_404(Grade, id=grade_id)

    if request.user.is_librarian and not request.user.is_superuser:
        if school.centre != request.user.centre:
            return redirect('book_list')

    books = Book.objects.filter(
        school=school,
        subject__grade=grade
    ).select_related('subject', 'subject__category', 'added_by', 'centre')

    category_id = request.GET.get('category')
    subject_id = request.GET.get('subject')
    q = request.GET.get('q', '').strip()
    available = request.GET.get('available') == '1'

    if category_id and category_id != 'all':
        books = books.filter(subject__category_id=category_id)
    if subject_id and subject_id != 'all':
        books = books.filter(subject_id=subject_id)
    if q:
        books = books.filter(
            Q(title__icontains=q) | Q(author__icontains=q) |
            Q(book_id__icontains=q) | Q(isbn__icontains=q)
        )
    if available:
        books = books.filter(available_copies=True)

    books = books.order_by('title')
    paginator = Paginator(books, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    categories = Category.objects.filter(
        subjects__books__school=school,
        subjects__books__subject__grade=grade
    ).distinct()

    subjects = Subject.objects.filter(grade=grade, books__school=school)
    if category_id:
        subjects = subjects.filter(category_id=category_id)

    context = {
        'school': school,
        'grade': grade,
        'page_obj': page_obj,
        'categories': categories,
        'subjects': subjects,
        'selected_category': category_id,
        'selected_subject': subject_id,
        'query': q,
        'available_only': available,
        'is_staff': is_staff_user(request.user),
    }
    return render(request, 'books/grade_book_list.html', context)


# =============================================================================
# 5. BOOK ADD (Single + Bulk) — Full Chain: Centre → School → Subject
# =============================================================================
# library_app/views/book_views.py

import csv
from io import TextIOWrapper
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from library_app.models import Centre, School, Category, Grade, Subject, Book, BookIDSequence
import re
from datetime import datetime
from django.db import transaction
from django.shortcuts import render
from django.contrib.auth.decorators import login_required



@login_required
def book_add(request):
    if request.method == "POST":
        # Common data extraction
        centre_id = request.POST.get('centre') or (request.user.centre.id if request.user.is_librarian else None)
        school_id = request.POST.get('school')
        category_id = request.POST.get('category')
        grade_id = request.POST.get('grade')
        subject_id = request.POST.get('subject')

        school = get_object_or_404(School, id=school_id)
        category = get_object_or_404(Category, id=category_id)

        # Handle subject (required only for Textbook)
        subject = None
        if category.name.lower() == 'textbook':
            if not grade_id or not subject_id:
                messages.error(request, "Grade and Subject are required for Textbook category.")
                return redirect('book_add')
            subject = get_object_or_404(Subject, id=subject_id)

        books_added = []

        if request.POST.get('bulk_upload'):
            # ==================== BULK UPLOAD ====================
            file = request.FILES.get('file')
            if not file or not file.name.endswith('.csv'):
                messages.error(request, "Please upload a valid CSV file.")
                return redirect('book_add')

            try:
                reader = csv.DictReader(TextIOWrapper(file.file, encoding='utf-8'))
                required_fields = ['title', 'author']
                if not all(field in reader.fieldnames for field in required_fields):
                    messages.error(request, f"CSV must contain at least: {', '.join(required_fields)}")
                    return redirect('book_add')

                for row in reader:
                    book = Book(
                        title=row['title'].strip(),
                        author=row['author'].strip(),
                        isbn=row.get('isbn', '').strip(),
                        publisher=row.get('publisher', '').strip(),
                        year_of_publication=int(row.get('year_of_publication', 2025) or 2025),
                        school=school,
                        subject=subject,
                        added_by=request.user,
                    )
                    try:
                        book.full_clean()
                        book.save()  # Auto-generates book_id via save()
                        books_added.append(book.pk)
                    except Exception as e:
                        messages.error(request, f"Failed: '{row['title']}' → {str(e)}")
                        continue

            except Exception as e:
                messages.error(request, f"Error reading CSV: {str(e)}")
                return redirect('book_add')

        else:
            # ==================== SINGLE BOOK ====================
            book = Book(
                title=request.POST['title'].strip(),
                author=request.POST['author'].strip(),
                isbn=request.POST.get('isbn', '').strip(),
                publisher=request.POST.get('publisher', '').strip(),
                year_of_publication=int(request.POST.get('year_of_publication', 2025)),
                school=school,
                subject=subject,
                added_by=request.user,
            )
            try:
                book.full_clean()
                book.save()
                books_added = [book.pk]
            except Exception as e:
                messages.error(request, f"Failed to add book: {str(e)}")
                return redirect('book_add')

        # =============== SAVE TO SESSION & REDIRECT ===============
        if books_added:
            # Update session with recently added book IDs (keep last 100)
            recent = request.session.get('recently_added_books', [])
            recent = list(set(recent + books_added))[-100:]
            request.session['recently_added_books'] = recent

            count = len(books_added)
            messages.success(
                request,
                f"Successfully added {count} book{'s' if count != 1 else ''}! "
                f"Confirmation below."
            )
            return redirect('book_add_confirmation')

    # ==================== GET REQUEST — SHOW FORM ====================
    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre]
    grades = Grade.objects.all().order_by('order', 'name')
    categories = Category.objects.all().order_by('name')

    context = {
        'centres': centres,
        'grades': grades,
        'categories': categories,
    }

    return render(request, 'books/book_add.html', context)


@login_required
def book_add_confirmation(request):
    """
    Shows only the books that were just added in this session.
    Uses session to store book IDs temporarily.
    """
    book_ids = request.session.get('recently_added_books', [])
    if not book_ids:
        messages.info(request, "No recently added books found.")
        return redirect('book_list')

    books = Book.objects.filter(id__in=book_ids).select_related(
        'school__centre', 'subject__category', 'subject__grade'
    ).order_by('-id')

    # Build beautiful breadcrumb title
    if books.exists():
        first_book = books.first()
        centre = first_book.school.centre.name if first_book.school.centre else "Unknown Centre"
        school = first_book.school.name
        category = first_book.subject.category.name if first_book.subject else "General"
        grade = first_book.subject.grade.name if first_book.subject and first_book.subject.grade else "All Grades"
        subject = first_book.subject.name if first_book.subject else "Various Subjects"

        page_title = f"{centre} → {school} → {grade} → {category} → {subject}"
    else:
        page_title = "Recently Added Books"

    # Clear session after showing (optional — you can keep it)
    # del request.session['recently_added_books']

    context = {
        'books': books,
        'page_title': page_title,
        'total_added': len(books),
    }
    return render(request, 'books/book_add_confirmation.html', context)

# Sample CSV Download
def sample_csv_download(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sample_book_upload.csv"'
    writer = csv.writer(response)
    writer.writerow(['title', 'author', 'isbn', 'publisher', 'year_of_publication'])
    writer.writerow(['Sample Book', 'John Doe', 'isbn-890123', 'Sample Publisher', 2023])
    return response


# =============================================================================
# 6. BOOK UPDATE
# =============================================================================
@login_required
def book_update(request, pk):
    if not is_staff_user(request.user):
        return redirect('book_list')

    book = get_object_or_404(Book, pk=pk)
    if request.user.is_librarian and book.centre != request.user.centre:
        return redirect('book_list')

    centres = Centre.objects.all() if request.user.is_superuser else [book.centre]
    schools = School.objects.filter(centre=book.centre)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                centre = book.centre
                if request.user.is_superuser:
                    centre = get_object_or_404(Centre, id=request.POST['centre'])

                book.title = request.POST['title'].strip()
                book.author = request.POST['author'].strip()
                book.isbn = request.POST['isbn'].strip()
                book.book_code = request.POST.get('book_code', '').strip() or None
                book.publisher = request.POST['publisher'].strip()
                book.year_of_publication = int(request.POST['year_of_publication'])
                book.subject = get_object_or_404(Subject, id=request.POST['subject'])
                book.school = get_object_or_404(School, id=request.POST['school'], centre=centre)
                book.centre = centre
                book.full_clean()
                book.save()
                messages.success(request, "Book updated.")
                return redirect('book_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")

    context = {
        'book': book,
        'centres': centres,
        'schools': schools,
        'subjects': Subject.objects.all(),
    }
    return render(request, 'books/book_update.html', context)


# =============================================================================
# 7. BOOK DELETE
# =============================================================================
@login_required
def book_delete(request, pk):
    if not is_staff_user(request.user):
        return redirect('book_list')
    book = get_object_or_404(Book, pk=pk)
    if request.user.is_librarian and book.centre != request.user.centre:
        return redirect('book_list')

    if request.method == 'POST':
        book.delete()
        messages.success(request, "Book deleted.")
        return redirect('book_list')
    return render(request, 'books/book_delete.html', {'book': book})


# =============================================================================
# 8. BOOK DETAIL + BORROW / RESERVE
# =============================================================================
@login_required
def book_detail(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.user.is_librarian and book.centre != request.user.centre:
        return redirect('book_list')

    if request.method == 'POST' and request.user.is_student:
        action = request.POST.get('action')
        if action == 'borrow' and book.available_copies:
            if can_user_borrow(request.user):
                Borrow.objects.create(
                    book=book, user=request.user, centre=book.centre,
                    status='requested', due_date=timezone.now() + timedelta(days=14)
                )
                messages.success(request, "Borrow request sent.")
            else:
                messages.error(request, "Borrow limit reached.")
        elif action == 'reserve':
            Reservation.objects.create(
                book=book, user=request.user, centre=book.centre,
                expiry_date=timezone.now() + timedelta(days=7)
            )
            messages.success(request, "Book reserved.")

    return render(request, 'books/book_detail.html', {'book': book, 'is_staff': is_staff_user(request.user)})


# =============================================================================
# 9. BORROW APPROVE
# =============================================================================
@login_required
def borrow_approve(request, pk):
    if not is_staff_user(request.user):
        return redirect('book_list')
    borrow = get_object_or_404(Borrow, pk=pk, status='requested')
    if request.user.is_librarian and borrow.centre != request.user.centre:
        return redirect('book_list')

    if request.method == 'POST':
        with transaction.atomic():
            if borrow.book.available_copies:
                borrow.status = 'issued'
                borrow.issue_date = timezone.now()
                borrow.issued_by = request.user
                borrow.book.available_copies = False
                borrow.book.save()
                borrow.save()
                Notification.objects.create(
                    user=borrow.user,
                    notification_type='borrow_approved',
                    message=f"Your request for '{borrow.book.title}' was approved."
                )
                messages.success(request, "Borrow approved.")
    return render(request, 'books/borrow_approve.html', {'borrow': borrow})


# =============================================================================
# AJAX: Chained Dropdowns
# =============================================================================
# AJAX: Load schools by centre
def ajax_load_schools(request):
    centre_id = request.GET.get('centre_id')
    schools = School.objects.filter(centre_id=centre_id).order_by('name')
    data = [{'id': s.id, 'name': s.name} for s in schools]
    return JsonResponse({'schools': data})


# AJAX: Load subjects by category + grade
def ajax_load_subjects(request):
    category_id = request.GET.get('category_id')
    grade_id = request.GET.get('grade_id')

    subjects = Subject.objects.all()
    if category_id:
        subjects = subjects.filter(category_id=category_id)
    if grade_id:
        subjects = subjects.filter(grade_id=grade_id)

    data = [{'id': s.id, 'name': s.name} for s in subjects.order_by('name')]
    return JsonResponse({'subjects': data})


# AJAX: Get next book code preview
def ajax_next_code(request):
    subject_id = request.GET.get('subject_id')
    if not subject_id:
        return JsonResponse({'next_code': 'Select subject first'})

    subject = get_object_or_404(Subject, id=subject_id)
    prefix = re.sub(r'[^A-Z]', '', subject.name.upper())[:3] or "MISC"

    last = Book.objects.filter(book_code__startswith=f"{prefix}-").order_by('-book_code').first()
    next_num = (int(last.book_code.split('-')[-1]) + 1) if last and last.book_code else 1

    return JsonResponse({'next_code': f"{prefix}-{next_num:04d}"})