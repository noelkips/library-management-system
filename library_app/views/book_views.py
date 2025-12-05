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
from django.core.exceptions import ValidationError
import csv
import openpyxl
import re
from io import TextIOWrapper
from datetime import timedelta, datetime
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

    # ==================================================================
    # 1. Superuser / Site Admin → Full Centre List
    # ==================================================================
    if user.is_superuser or user.is_site_admin:
        centres = Centre.objects.annotate(
            school_count=Count('schools', distinct=True),
            book_count=Count('books')
        ).order_by('-book_count', 'name')

        total_schools = sum(c.school_count for c in centres)
        total_books   = sum(c.book_count   for c in centres)

        return render(request, 'books/centre_list.html', {
            'centres': centres,
            'title': 'Library Centres',
            'total_schools': total_schools,
            'total_books': total_books,
        })

    # ==================================================================
    # 2. ALL STAFF: Librarian, Teacher, Regular Staff → School List from their centre
    # ==================================================================
    if user.centre and (user.is_librarian or user.is_teacher or getattr(user, 'is_other', False)):
        schools = user.centre.schools.all().annotate(book_count=Count('books'))
        
        total_books = sum(s.book_count for s in schools)
        active_borrows = Borrow.objects.filter(centre=user.centre, status='issued').count()
        available_books = Book.objects.filter(school__centre=user.centre, available_copies__gt=0).count()

        # If only one school → go directly to catalog
        if schools.count() == 1:
            return redirect('school_catalog', school_id=schools.first().id)

        return render(request, 'books/school_list.html', {
            'centre': user.centre,
            'schools': schools,
            'total_books': total_books,
            'active_borrows': active_borrows,
            'available_books': available_books,
        })

    # ==================================================================
    # 3. Student → Direct to their school
    # ==================================================================
    if user.is_student and hasattr(user, 'student_profile') and user.student_profile.school:
        return redirect('school_catalog', school_id=user.student_profile.school.id)

    # ==================================================================
    # 4. Fallback
    # ==================================================================
    messages.error(request, "You do not have access to any library.")
    return redirect('dashboard')


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

    # ==================================================================
    # Permission Check for Librarians (non-superusers)
    # ==================================================================
    if request.user.is_librarian and not request.user.is_superuser:
        if school.centre != request.user.centre:
            messages.error(request, "You do not have permission to access this school.")
            return redirect('book_list')

    # ==================================================================
    # Get active tab: textbooks (default) or other
    # ==================================================================
    active_tab = request.GET.get('tab', 'textbooks')  # 'textbooks' or 'other'

    # ==================================================================
    # TEXTBOOKS TAB — Grade + Subject Based
    # ==================================================================
    if active_tab != 'other':
        selected_subject_id = request.GET.get('subject')

        # All subjects that have textbooks in this school
        textbook_subjects = Subject.objects.filter(
            grade__isnull=False,
            books__school=school
        ).annotate(book_count=Count('books')).distinct().order_by('name')

        selected_subject = None
        if selected_subject_id:
            selected_subject = get_object_or_404(Subject, id=selected_subject_id, grade__isnull=False)

        # Grades with book counts
        grades = Grade.objects.annotate(
            total_books=Count(
                'subjects__books',
                filter=Q(subjects__books__school=school),
                distinct=True
            ),
            filtered_books=Count(
                'subjects__books',
                filter=Q(subjects__books__school=school) &
                       (Q(subjects=selected_subject) if selected_subject else Q()),
                distinct=True
            )
        ).order_by('order', 'name')

        # Only show grades that have books in the selected subject (or all if no subject selected)
        filtered_grades = [
            g for g in grades
            if (selected_subject and g.filtered_books > 0) or (not selected_subject and g.total_books > 0)
        ]

        total_textbooks = sum(g.total_books for g in grades)

        context = {
            'school': school,
            'grades': grades,
            'filtered_grades': filtered_grades,
            'textbook_subjects': textbook_subjects,
            'selected_subject': selected_subject,
            'total_textbooks': total_textbooks,
            'active_tab': 'textbooks',
            'is_staff': is_staff_user(request.user),
        }

        return render(request, 'books/school_catalog.html', context)

    # ==================================================================
    # OTHER BOOKS TAB — Category Based Table List
    # ==================================================================
    else:
        selected_category_id = request.GET.get('category')
        query = request.GET.get('q', '').strip()
        available_only = request.GET.get('available') == 'on'

        # Base queryset: only non-textbook books
        books = Book.objects.filter(
            school=school,
            subject__grade__isnull=True  # This excludes textbooks
        ).select_related('subject', 'subject__category').order_by('book_id')

        # Filter by category
        if selected_category_id:
            books = books.filter(subject__category_id=selected_category_id)

        # Search
        if query:
            books = books.filter(
                Q(title__icontains=query) |
                Q(author__icontains=query) |
                Q(isbn__icontains=query) |
                Q(book_id__icontains=query)
            )

        # Availability
        if available_only:
            books = books.filter(available_copies__gt=0)

        # Categories with book counts
        categories = Category.objects.annotate(
            book_count=Count(
                'subjects__books',
                filter=Q(subjects__books__school=school, subjects__grade__isnull=True),
                distinct=True
            )
        ).exclude(book_count=0).order_by('name')

        selected_category = None
        if selected_category_id:
            selected_category = get_object_or_404(Category, id=selected_category_id)

        # Pagination
        paginator = Paginator(books, 25)
        page_obj = paginator.get_page(request.GET.get('page'))

        context = {
            'school': school,
            'page_obj': page_obj,
            'categories': categories,
            'selected_category': selected_category,
            'query': query,
            'available_only': available_only,
            'active_tab': 'other',
            'is_staff': is_staff_user(request.user),
        }

        return render(request, 'books/other_books_list.html', context)

# =============================================================================
# 4. FINAL BOOK LIST: Grade + Category + Subject Filter (FIXED & IMPROVED)
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

    category_id = request.GET.get('category', '').strip()
    subject_id = request.GET.get('subject', '').strip()
    q = request.GET.get('q', '').strip()
    available = request.GET.get('available') == 'on'  # Changed to 'on' for checkbox

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

    # Export Logic
    if 'export' in request.GET:
        export_type = request.GET['export']
        if export_type == 'page':
            books_to_export = Paginator(books, 20).get_page(request.GET.get('page')).object_list
        elif export_type == 'all':
            books_to_export = books
        else:
            books_to_export = []

        if books_to_export.exists():
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{grade.name}_books.xlsx"'
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(['Title', 'Author', 'ISBN', 'Status'])
            for book in books_to_export:
                status = 'Available' if book.available_copies else 'Borrowed'
                ws.append([book.title, book.author, book.isbn or '', status])
            wb.save(response)
            return response

    # Pagination (after filters, before export)
    paginator = Paginator(books, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    categories = Category.objects.filter(
        subjects__books__school=school,
        subjects__books__subject__grade=grade
    ).distinct()

    subjects = Subject.objects.filter(grade=grade, books__school=school).distinct()
    if category_id and category_id != 'all':
        subjects = subjects.filter(category_id=category_id)

    context = {
        'school': school,
        'grade': grade,
        'page_obj': page_obj,
        'categories': categories,
        'subjects': subjects,
        'selected_category': category_id if category_id != 'all' else None,
        'selected_subject': subject_id if subject_id != 'all' else None,
        'query': q,
        'available_only': available,
        'is_staff': is_staff_user(request.user),
    }
    return render(request, 'books/grade_book_list.html', context)

# =============================================================================
# 5. BOOK ADD (Single + Bulk) — Full Chain: Centre → School → Subject
# =============================================================================


@login_required
def book_add(request):
    if not is_staff_user(request.user):
        messages.error(request, "You don't have permission to add books.")
        return redirect('book_list')

    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre]
    categories = Category.objects.all().order_by('name')
    grades = Grade.objects.all().order_by('order', 'name')

    if request.method == "POST":
        try:
            with transaction.atomic():
                # === Centre ===
                centre = request.user.centre
                if request.user.is_superuser:
                    centre_id = request.POST.get('centre')
                    if not centre_id:
                        messages.error(request, "Centre is required.")
                        return redirect('book_add')
                    centre = get_object_or_404(Centre, id=centre_id)

                # === School ===
                school_id = request.POST.get('school')
                if not school_id:
                    messages.error(request, "School is required.")
                    return redirect('book_add')
                school = get_object_or_404(School, id=school_id, centre=centre)

                # === Category ===
                category_id = request.POST.get('category')
                if not category_id:
                    messages.error(request, "Category is required.")
                    return redirect('book_add')
                category = get_object_or_404(Category, id=category_id)

                # === Subject (only for Textbook) ===
                subject = None
                if category.name.lower() == 'textbook':
                    grade_id = request.POST.get('grade')
                    subject_id = request.POST.get('subject')
                    if not grade_id or not subject_id:
                        messages.error(request, "Textbook requires Grade and Subject.")
                        return redirect('book_add')
                    subject = get_object_or_404(Subject, id=subject_id, grade_id=grade_id, category=category)

                added_books = []  # To store successfully created Book instances
                errors = []

                # ==================== BULK UPLOAD ====================
                if 'bulk_upload' in request.POST:
                    csv_file = request.FILES.get('file')
                    if not csv_file:
                        messages.error(request, "Please upload a CSV file.")
                        return redirect('book_add')
                    if not csv_file.name.lower().endswith('.csv'):
                        messages.error(request, "File must be a .csv")
                        return redirect('book_add')

                    try:
                        reader = csv.DictReader(TextIOWrapper(csv_file.file, encoding='utf-8-sig'))
                        expected_headers = {'title', 'author', 'isbn', 'publisher', 'year_of_publication'}
                        if not expected_headers.issubset(set(reader.fieldnames or [])):
                            messages.error(request, "CSV missing required columns: title, author")
                            return redirect('book_add')

                        for row_num, row in enumerate(reader, start=2):
                            title = row.get('title', '').strip()
                            author = row.get('author', '').strip()
                            if not title or not author:
                                errors.append(f"Row {row_num}: Missing title or author")
                                continue

                            try:
                                book = Book(
                                    title=title,
                                    author=author,
                                    isbn=row.get('isbn', '').strip(),
                                    publisher=row.get('publisher', '').strip() or "Unknown",
                                    year_of_publication=int(row.get('year_of_publication', 2025) or 2025),
                                    school=school,
                                    centre=centre,
                                    subject=subject,
                                    added_by=request.user,
                                )
                                book.full_clean()
                                book.save()
                                added_books.append(book)
                            except Exception as e:
                                errors.append(f"Row {row_num} ('{title}'): {str(e)}")
                    except Exception as e:
                        messages.error(request, f"CSV processing error: {str(e)}")
                        return redirect('book_add')

                # ==================== SINGLE BOOK ====================
                else:
                    title = request.POST.get('title', '').strip()
                    author = request.POST.get('author', '').strip()
                    if not title or not author:
                        messages.error(request, "Title and Author are required.")
                        return redirect('book_add')

                    book = Book(
                        title=title,
                        author=author,
                        isbn=request.POST.get('isbn', '').strip(),
                        publisher=request.POST.get('publisher', '').strip() or "Unknown",
                        year_of_publication=int(request.POST.get('year_of_publication', 2025)),
                        school=school,
                        centre=centre,
                        subject=subject,
                        added_by=request.user,
                    )
                    book.full_clean()
                    book.save()
                    added_books.append(book)

                # === SUCCESS: Store in session + redirect ===
                if added_books:
                    # Store only the IDs of books added in this request
                    request.session['just_added_book_ids'] = [b.id for b in added_books]
                    request.session['just_added_count'] = len(added_books)

                    msg = f"Successfully added {len(added_books)} book{'s' if len(added_books) > 1 else ''}!"
                    if errors:
                        msg += f" {len(errors)} row(s) had errors."
                        for err in errors[:5]:
                            messages.warning(request, err)
                        if len(errors) > 5:
                            messages.warning(request, f"...and {len(errors)-5} more.")
                    messages.success(request, msg)
                    return redirect('book_add_confirmation')

                else:
                    for err in errors:
                        messages.error(request, err)
                    messages.error(request, "No books were added due to errors.")

        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
            return redirect('book_add')

    context = {
        'centres': centres,
        'categories': categories,
        'grades': grades,
    }
    return render(request, 'books/book_add.html', context)


@login_required
def book_add_confirmation(request):
    book_ids = request.session.get('just_added_book_ids', [])
    count = request.session.get('just_added_count', 0)

    if not book_ids:
        messages.info(request, "No books were added in this session.")
        return redirect('book_list')

    books = Book.objects.filter(id__in=book_ids).select_related(
        'school__centre', 'subject__grade', 'subject__category'
    ).order_by('-id')

    # Clear session after displaying
    del request.session['just_added_book_ids']
    del request.session['just_added_count']

    # Smart page title
    if books.exists():
        first = books.first()
        centre_name = first.centre.name if first.centre else "Unknown"
        school_name = first.school.name
        cat_name = first.subject.category.name if first.subject else "General"
        grade_name = first.subject.grade.name if first.subject and first.subject.grade else "All Grades"
        page_title = f"{centre_name} → {school_name} → {grade_name} → {cat_name}"
    else:
        page_title = "Books Added"

    context = {
        'books': books,
        'total_added': count,
        'page_title': page_title,
    }
    return render(request, 'books/book_add_confirmation.html', context)
# =============================================================================
# SAMPLE CSV DOWNLOAD
# =============================================================================
@login_required
def sample_csv_download(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sample_books_upload.csv"'
    writer = csv.writer(response)
    writer.writerow(['title', 'author', 'isbn', 'publisher', 'year_of_publication'])
    writer.writerow(['The Great Gatsby', 'F. Scott Fitzgerald', '978-0-7432-7356-5', 'Scribner', '1925'])
    writer.writerow(['Mathematics Grade 10', 'John Doe', '978-1-234567-89-0', 'National Press', '2023'])
    return response

# =============================================================================
# 6. BOOK UPDATE
# =============================================================================

@login_required
def book_update(request, pk):
    if not is_staff_user(request.user):
        messages.error(request, "Access denied.")
        return redirect('book_list')

    book = get_object_or_404(Book, pk=pk)

    # Restrict librarian to their own centre
    if request.user.is_librarian and book.centre != request.user.centre:
        messages.error(request, "You can only edit books from your centre.")
        return redirect('book_list')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # 1. Centre (superuser only)
                if request.user.is_superuser:
                    centre_id = request.POST.get('centre')
                    if not centre_id:
                        raise ValidationError("Centre is required.")
                    centre = get_object_or_404(Centre, id=centre_id)
                else:
                    centre = book.centre

                # 2. Update basic fields
                book.title = request.POST['title'].strip()
                book.author = request.POST['author'].strip()
                book.isbn = request.POST.get('isbn', '').strip()
                book.publisher = request.POST.get('publisher', '').strip()
                book.year_of_publication = int(request.POST['year_of_publication'])
                book.book_code = request.POST.get('book_code', '').strip() or None

                # 3. SCHOOL — MUST BE SET BEFORE SUBJECT (critical for validation!)
                school_id = request.POST.get('school')
                if not school_id:
                    raise ValidationError("Please select a school.")
                book.school = get_object_or_404(School, id=school_id, centre=centre)

                # 4. CATEGORY
                category_id = request.POST.get('category')
                if not category_id:
                    raise ValidationError("Please select a category.")
                category = get_object_or_404(Category, id=category_id)

                # 5. SUBJECT — ONLY FOR TEXTBOOK
                if category.name.lower() == 'textbook':
                    grade_id = request.POST.get('grade')
                    subject_id = request.POST.get('subject')

                    if not grade_id or not subject_id:
                        raise ValidationError("Grade and Subject are required for Textbook category.")

                    # Validate subject belongs to the selected grade
                    book.subject = get_object_or_404(
                        Subject,
                        id=subject_id,
                        grade_id=grade_id
                    )
                else:
                    book.subject = None  # Non-textbook

                # 6. Final assignments
                book.centre = centre

                # 7. Validate (now school + subject are in correct order)
                book.full_clean()  # This runs your clean() method safely
                book.save()

                messages.success(request, f"Book '{book.title}' updated successfully!")
                return redirect('book_detail', pk=book.pk)

        except ValidationError as e:
            # Catch Django ValidationError (from clean()) and non-field errors
            messages.error(request, f"Update failed: {' '.join(e.messages)}")
        except Exception as e:
            messages.error(request, f"Update failed: {str(e)}")

    # ——— GET REQUEST ———
    centres = Centre.objects.all() if request.user.is_superuser else [book.centre]
    schools = book.centre.schools.all()

    context = {
        'book': book,
        'centres': centres,
        'schools': schools,
        'categories': Category.objects.all(),
        'grades': Grade.objects.all(),
        'current_category': book.subject.category if book.subject else None,
        'current_grade': book.subject.grade if book.subject else None,
        'current_subject': book.subject,
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