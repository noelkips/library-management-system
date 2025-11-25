from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404
from django.utils import timezone
import csv
import openpyxl
from io import TextIOWrapper
from ..models import Book, Centre, CustomUser, Category, Borrow, Reservation, Notification, Grade, Subject, can_user_borrow
from datetime import timedelta
from django.core.exceptions import ValidationError

def is_authorized(user):
    return user.is_superuser or user.is_librarian

def handle_uploaded_file(request, file, user, centre_id, category_id, grade_id, subject_id):
    header_mapping = {
        'book_title': 'title',
        'author_name': 'author',
        'book_code': 'book_code',
        'isbn': 'isbn',
        'publisher': 'publisher',
        'pub_year': 'year_of_publication',
    }

    errors = []
    created_count = 0
    skipped_count = 0
    total_rows = 0

    try:
        centre = None
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
            except Centre.DoesNotExist:
                messages.error(request, f"Selected centre with ID {centre_id} not found.")
                return

        if user.is_librarian and not user.is_superuser and user.centre and centre != user.centre:
            messages.error(request, "You can only add books for your own centre.")
            return

        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            messages.error(request, f"Selected category with ID {category_id} not found.")
            return

        # Fetch Grade and Subject if provided
        grade = None
        if grade_id:
            try:
                grade = Grade.objects.get(id=grade_id)
            except Grade.DoesNotExist:
                pass
        
        subject = None
        if subject_id:
            try:
                subject = Subject.objects.get(id=subject_id)
            except Subject.DoesNotExist:
                pass

        # Validate mandatory fields for Textbook category
        if category.name.lower() == 'textbook':
            if not grade:
                messages.error(request, "Grade is mandatory for Textbook category.")
                return
            if not subject:
                messages.error(request, "Subject is mandatory for Textbook category.")
                return

        book_instances = []
        if file.name.lower().endswith('.csv'):
            file.seek(0)
            decoded_file = TextIOWrapper(file.file, encoding='utf-8-sig')
            reader = csv.reader(decoded_file)
            headers = next(reader, None)
            if not headers:
                messages.error(request, "File is empty or has no headers.")
                return
            headers = [h.lower().strip() for h in headers]

            if not all(h in headers for h in ['isbn', 'book_title', 'author_name', 'publisher', 'pub_year']):
                messages.error(request, "CSV file must include 'isbn', 'book_title', 'author_name', 'publisher', and 'pub_year' columns.")
                return

            all_rows = list(reader)
            total_rows = len(all_rows) + 1

            for row_index, row in enumerate(all_rows, start=2):
                if not any(row):
                    skipped_count += 1
                    continue
                data = {header_mapping.get(header, header): value.strip() if value else None for header, value in zip(headers, row) if header in header_mapping}
                if not all(data.get(k) for k in ['title', 'author', 'isbn', 'publisher', 'year_of_publication']):
                    errors.append(f"Row {row_index}: Missing required fields")
                    continue
                isbn = data.get('isbn')
                if len(isbn) < 8 or len(isbn) > 18:
                    errors.append(f"Row {row_index}: ISBN must be between 8 and 18 characters")
                    continue
                try:
                    year = int(data.get('year_of_publication'))
                    if year < 1500 or year > 2025:
                        errors.append(f"Row {row_index}: Year must be between 1500 and 2025")
                        continue
                except (ValueError, TypeError):
                    errors.append(f"Row {row_index}: Invalid year format")
                    continue
                book_instances.append((row_index, data))

        elif file.name.lower().endswith('.xlsx'):
            wb = openpyxl.load_workbook(file)
            ws = wb.active
            headers = [cell.value.lower().strip() if cell.value else '' for cell in ws[1]]
            if not headers:
                messages.error(request, "Excel file is empty or has no headers.")
                return

            if not all(h in headers for h in ['isbn', 'book_title', 'author_name', 'publisher', 'pub_year']):
                messages.error(request, "Excel file must include 'isbn', 'book_title', 'author_name', 'publisher', and 'pub_year' columns.")
                return

            all_rows = list(ws.iter_rows(min_row=2))
            total_rows = len(all_rows) + 1

            for row_index, row in enumerate(all_rows, start=2):
                data = {header_mapping.get(headers[i], headers[i]): cell.value if cell.value else None for i, cell in enumerate(row) if i < len(headers) and headers[i] in header_mapping}
                if not all(data.get(k) for k in ['title', 'author', 'isbn', 'publisher', 'year_of_publication']):
                    errors.append(f"Row {row_index}: Missing required fields")
                    continue
                isbn = str(data.get('isbn'))
                if len(isbn) < 8 or len(isbn) > 18:
                    errors.append(f"Row {row_index}: ISBN must be between 8 and 18 characters")
                    continue
                try:
                    year = int(data.get('year_of_publication'))
                    if year < 1500 or year > 2025:
                        errors.append(f"Row {row_index}: Year must be between 1500 and 2025")
                        continue
                except (ValueError, TypeError):
                    errors.append(f"Row {row_index}: Invalid year format")
                    continue
                book_instances.append((row_index, data))

        else:
            messages.error(request, "Unsupported file format. Only CSV and XLSX are allowed.")
            return

        for row_index, data in book_instances:
            try:
                with transaction.atomic():
                    book = Book(
                        title=data.get('title'),
                        author=data.get('author'),
                        category=category,
                        grade=grade, # Added Grade
                        subject=subject, # Added Subject
                        book_code=data.get('book_code'),
                        isbn=str(data.get('isbn')),
                        publisher=data.get('publisher'),
                        year_of_publication=int(data.get('year_of_publication')),
                        centre=centre or (user.centre if user.is_librarian and not user.is_superuser else None),
                        added_by=user,
                        available_copies=True
                    )
                    book.full_clean()
                    book.save(user=user)
                    created_count += 1
            except ValidationError as e:
                errors.append(f"Row {row_index}: {', '.join([f'{field}: {msg}' for field, msg in e.message_dict.items()])}")
            except IntegrityError:
                errors.append(f"Row {row_index}: Book with ISBN {data.get('isbn')} or book_code {data.get('book_code')} already exists")
            except Exception as e:
                errors.append(f"Row {row_index}: Error saving ({str(e)})")

        if created_count > 0:
            messages.success(request, f"{created_count} books imported successfully.", extra_tags='green')
        if errors:
            messages.error(request, f"Failed to import {len(errors)} rows: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''}")
        messages.info(request, f"Processed {total_rows} rows: {created_count} added, {len(errors)} failed, {skipped_count} skipped.")

        if created_count == 0 and not errors:
            messages.error(request, "No books were imported. Please check the file format and data.")

    except Exception as e:
        messages.error(request, f"Error processing file: {str(e)}")

@login_required
def book_add(request):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('book_list')

    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []
    categories = Category.objects.all()
    grades = Grade.objects.all()
    subjects = Subject.objects.all()

    if request.method == 'POST':
        # Handle bulk upload
        if 'file' in request.FILES and request.FILES['file']:
            centre_id = request.POST.get('bulk_centre')
            category_id = request.POST.get('bulk_category')
            grade_id = request.POST.get('bulk_grade')
            subject_id = request.POST.get('bulk_subject')

            if not centre_id or not category_id:
                messages.error(request, "Please select both a centre and a category for bulk upload.")
                return render(request, 'books/book_add.html', {
                    'centres': centres,
                    'categories': categories,
                    'grades': grades,
                    'subjects': subjects,
                    'form_data': request.POST
                })
            
            try:
                handle_uploaded_file(request, request.FILES['file'], request.user, centre_id, category_id, grade_id, subject_id)
                return redirect('book_list')
            except Exception as e:
                messages.error(request, f"Error uploading books: {str(e)}")
                return render(request, 'books/book_add.html', {
                    'centres': centres,
                    'categories': categories,
                    'grades': grades,
                    'subjects': subjects,
                    'form_data': request.POST
                })

        # Handle single book addition
        try:
            with transaction.atomic():
                title = request.POST.get('title', '').strip()
                author = request.POST.get('author', '').strip()
                category_id = request.POST.get('category')
                grade_id = request.POST.get('grade')
                subject_id = request.POST.get('subject')
                book_code = request.POST.get('book_code', '').strip() or None
                isbn = request.POST.get('isbn', '').strip()
                publisher = request.POST.get('publisher', '').strip()
                year_of_publication = request.POST.get('year_of_publication', '').strip()
                centre_id = request.POST.get('centre')

                # Basic validations (Detailed validations are in model.clean)
                if not title or not author or not publisher or not year_of_publication or not isbn or not category_id:
                     messages.error(request, "All required fields must be filled.")
                     return render(request, 'books/book_add.html', {
                        'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST
                    })

                # Validate centre
                try:
                    centre = Centre.objects.get(id=centre_id) if centre_id else None
                    if request.user.is_librarian and not request.user.is_superuser:
                        centre = request.user.centre
                        if centre_id and int(centre_id) != centre.id:
                            messages.error(request, "You can only add books for your own centre.")
                            return render(request, 'books/book_add.html', {
                                'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST
                            })
                    if not centre:
                        messages.error(request, "Centre is required.")
                        return render(request, 'books/book_add.html', {
                            'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST
                        })
                except Centre.DoesNotExist:
                    messages.error(request, "Invalid centre selected.")
                    return render(request, 'books/book_add.html', {
                        'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST
                    })

                # Get Objects
                try:
                    category = Category.objects.get(id=category_id)
                except Category.DoesNotExist:
                    messages.error(request, "Invalid category selected.")
                    return render(request, 'books/book_add.html', { 'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST })

                grade = None
                if grade_id:
                    grade = Grade.objects.get(id=grade_id)
                
                subject = None
                if subject_id:
                    subject = Subject.objects.get(id=subject_id)

                # Create book instance
                book = Book(
                    title=title,
                    author=author,
                    category=category,
                    grade=grade,
                    subject=subject,
                    book_code=book_code,
                    isbn=isbn,
                    publisher=publisher,
                    year_of_publication=int(year_of_publication),
                    centre=centre,
                    added_by=request.user,
                    is_active=True,
                    available_copies=True
                )

                # Validate and save (clean method checks for textbook requirements)
                try:
                    book.full_clean()
                    book.save(user=request.user)
                    messages.success(request, f"Book '{book.title}' added successfully.", extra_tags='green')
                    return redirect('book_list')
                except ValidationError as e:
                    for field, errors in e.message_dict.items():
                        messages.error(request, f"{field.capitalize()}: {', '.join(errors)}")
                    return render(request, 'books/book_add.html', {
                        'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST
                    })
                except IntegrityError:
                    messages.error(request, "Book with this ISBN or book_code already exists.")
                    return render(request, 'books/book_add.html', {
                        'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST
                    })

        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
            return render(request, 'books/book_add.html', {
                'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST
            })

    return render(request, 'books/book_add.html', {
        'centres': centres,
        'categories': categories,
        'grades': grades,
        'subjects': subjects,
        'form_data': {}
    })

@login_required
def book_update(request, pk):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('book_list')

    book = get_object_or_404(Book, pk=pk)
    if request.user.is_librarian and not request.user.is_superuser and book.centre != request.user.centre:
        messages.error(request, "You can only update books for your own centre.")
        return redirect('book_list')

    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []
    categories = Category.objects.all()
    grades = Grade.objects.all()
    subjects = Subject.objects.all()

    if request.method == 'POST':
        try:
            with transaction.atomic():
                title = request.POST.get('title', book.title).strip()
                author = request.POST.get('author', book.author).strip()
                category_id = request.POST.get('category', str(book.category_id))
                grade_id = request.POST.get('grade')
                subject_id = request.POST.get('subject')
                book_code = request.POST.get('book_code', book.book_code).strip() or None
                isbn = request.POST.get('isbn', book.isbn).strip()
                publisher = request.POST.get('publisher', book.publisher).strip()
                year_of_publication = request.POST.get('year_of_publication', str(book.year_of_publication)).strip()
                centre_id = request.POST.get('centre', str(book.centre_id))

                # Retrieve Objects
                try:
                    centre = Centre.objects.get(id=centre_id) if centre_id else book.centre
                    category = Category.objects.get(id=category_id)
                except (Centre.DoesNotExist, Category.DoesNotExist):
                     messages.error(request, "Invalid centre or category.")
                     return render(request, 'books/book_update.html', {'book': book, 'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST})

                grade = None
                if grade_id:
                    grade = Grade.objects.get(id=grade_id)
                
                subject = None
                if subject_id:
                    subject = Subject.objects.get(id=subject_id)

                # Update book instance
                book.title = title
                book.author = author
                book.category = category
                book.grade = grade
                book.subject = subject
                book.book_code = book_code
                book.isbn = isbn
                book.publisher = publisher
                book.year_of_publication = int(year_of_publication)
                book.centre = centre

                # Validate and save
                try:
                    book.full_clean()
                    book.save(user=request.user)
                    messages.success(request, f"Book '{book.title}' updated successfully.", extra_tags='green')
                    return redirect('book_list')
                except ValidationError as e:
                    for field, errors in e.message_dict.items():
                        messages.error(request, f"{field.capitalize()}: {', '.join(errors)}")
                    return render(request, 'books/book_update.html', {
                        'book': book, 'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST
                    })
                except IntegrityError:
                    messages.error(request, "Book with this ISBN or book_code already exists.")
                    return render(request, 'books/book_update.html', {
                        'book': book, 'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST
                    })

        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
            return render(request, 'books/book_update.html', {
                'book': book, 'centres': centres, 'categories': categories, 'grades': grades, 'subjects': subjects, 'form_data': request.POST
            })

    return render(request, 'books/book_update.html', {
        'book': book,
        'centres': centres,
        'categories': categories,
        'grades': grades,
        'subjects': subjects,
        'form_data': {
            'title': book.title,
            'author': book.author,
            'book_code': book.book_code or '',
            'isbn': book.isbn,
            'publisher': book.publisher,
            'year_of_publication': book.year_of_publication,
            'category': book.category_id,
            'centre': book.centre_id,
            'grade': book.grade_id,
            'subject': book.subject_id
        }
    })

# ---------------------------------------------------
# NEW WORKFLOW: Step 1 - Category List (Replaces old book_list entry)
# ---------------------------------------------------
@login_required
def book_list(request):
    """
    Step 1: Displays cards for each Category with book counts.
    """
    if request.user.is_superuser:
        centres = Centre.objects.all()
        # Counts for superuser might need to be centre-specific in a real filter, 
        # but here we show total system counts or filtered by a centre GET param
    else:
        centres = [request.user.centre] if request.user.centre else []

    # Base query for counting
    books_query = Book.objects.all()
    
    # Filter by centre if librarian
    if request.user.is_librarian and request.user.centre:
        books_query = books_query.filter(centre=request.user.centre)
    
    # Filter by centre if passed in GET (admin)
    selected_centre_id = request.GET.get('centre')
    if selected_centre_id and request.user.is_superuser:
        books_query = books_query.filter(centre_id=selected_centre_id)

    # Annotate categories with book counts
    categories = Category.objects.annotate(
        num_books=Count('books', filter=Q(books__in=books_query))
    )

    return render(request, 'books/category_list.html', {
        'categories': categories,
        'centres': centres,
        'selected_centre': selected_centre_id
    })

# ---------------------------------------------------
# NEW WORKFLOW: Step 2 - Grade/Subject Selector
# ---------------------------------------------------
@login_required
def grade_subject_view(request, category_id):
    """
    Step 2: If category is Textbook, show Grade/Subject selection.
    Otherwise, redirect to list.
    """
    category = get_object_or_404(Category, pk=category_id)
    
    # Check if this is a "Textbook" category (case-insensitive)
    if category.name.lower() != 'textbook':
        # Skip this step for non-textbooks
        return redirect('final_book_list', category_id=category_id)

    # Base Query for stats
    books_query = Book.objects.filter(category=category)
    if request.user.is_librarian and request.user.centre:
        books_query = books_query.filter(centre=request.user.centre)
    
    # Annotate Grades and Subjects with counts
    grades = Grade.objects.annotate(
        num_books=Count('books', filter=Q(books__in=books_query))
    ).order_by('name')
    
    subjects = Subject.objects.annotate(
        num_books=Count('books', filter=Q(books__in=books_query))
    ).order_by('name')

    total_books = books_query.count()

    return render(request, 'books/grade_subject_selector.html', {
        'category': category,
        'grades': grades,
        'subjects': subjects,
        'total_books': total_books
    })

# ---------------------------------------------------
# NEW WORKFLOW: Step 3 - Final Book List
# ---------------------------------------------------
@login_required
def final_book_list(request, category_id):
    """
    Step 3: The actual table list of books, filtered by Category, Grade, Subject.
    """
    category = get_object_or_404(Category, pk=category_id)
    
    # Initial Filter
    books = Book.objects.filter(category=category)
    
    # Permission Filter
    if request.user.is_librarian and request.user.centre:
        books = books.filter(centre=request.user.centre)

    # Grade/Subject Filters (from GET params or logic)
    grade_id = request.GET.get('grade')
    subject_id = request.GET.get('subject')

    if grade_id and grade_id != 'all':
        books = books.filter(grade_id=grade_id)
    if subject_id and subject_id != 'all':
        books = books.filter(subject_id=subject_id)

    # Search Filter
    query = request.GET.get('q', '')
    if query:
        books = books.filter(
            Q(title__icontains=query) |
            Q(author__icontains=query) |
            Q(book_code__icontains=query) |
            Q(isbn__icontains=query)
        )
    
    available_only = 'available' in request.GET
    if available_only:
        books = books.filter(available_copies=True)

    books = books.order_by('title')

    # Pagination
    items_per_page = request.GET.get('items_per_page', '10')
    paginator = Paginator(books, int(items_per_page))
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Stats for the current view
    total_count = books.count()

    return render(request, 'books/book_list.html', {
        'page_obj': page_obj,
        'books': page_obj.object_list,
        'category': category,
        'selected_grade': grade_id,
        'selected_subject': subject_id,
        'query': query,
        'items_per_page': int(items_per_page),
        'grades': Grade.objects.all(),
        'subjects': Subject.objects.all(),
        'total_count': total_count
    })

@login_required
def book_detail(request, pk):
    book = get_object_or_404(Book, pk=pk)
    
    if request.user.is_librarian and not request.user.is_superuser and book.centre != request.user.centre:
        messages.error(request, "You can only view books for your own centre.")
        return redirect('book_list')

    if request.method == 'POST':
        if not request.user.is_student:
            messages.error(request, "Only students can borrow or reserve books.")
            return redirect('book_detail', pk=pk)

        action = request.POST.get('action')
        if action == 'borrow' and book.is_available():
            try:
                with transaction.atomic():
                    if not can_user_borrow(request.user):
                        messages.error(request, "You have reached your borrowing limit.")
                        return redirect('book_detail', pk=pk)
                    Borrow.objects.create(
                        book=book,
                        user=request.user,
                        centre=book.centre,
                        status='requested',
                        request_date=timezone.now(),
                        due_date=timezone.now() + timedelta(days=14),
                    )
                    messages.success(request, "Borrow request submitted successfully.", extra_tags='green')
                    return redirect('book_detail', pk=pk)
            except Exception as e:
                messages.error(request, f"Error requesting borrow: {str(e)}")
        elif action == 'reserve':
            try:
                with transaction.atomic():
                    if not can_user_borrow(request.user):
                        messages.error(request, "You have reached your borrowing limit.")
                        return redirect('book_detail', pk=pk)
                    Reservation.objects.create(
                        book=book,
                        user=request.user,
                        centre=book.centre,
                        expiry_date=timezone.now() + timedelta(days=7)
                    )
                    messages.success(request, "Book reserved successfully.", extra_tags='green')
                    return redirect('book_detail', pk=pk)
            except Exception as e:
                messages.error(request, f"Error reserving book: {str(e)}")
        else:
            messages.error(request, "Invalid action or book not available.")

    return render(request, 'books/book_detail.html', {
        'book': book,
    })


@login_required
def book_delete(request, pk):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('book_list')

    book = get_object_or_404(Book, pk=pk)
    if request.user.is_librarian and not request.user.is_superuser and book.centre != request.user.centre:
        messages.error(request, "You can only delete books for your own centre.")
        return redirect('book_list')

    if request.method == 'POST':
        try:
            book_title = book.title
            book.delete()
            messages.success(request, f"Book '{book_title}' deleted successfully.", extra_tags='green')
            return redirect('book_list')
        except Exception as e:
            messages.error(request, f"Error deleting book: {str(e)}")
            return render(request, 'books/book_delete.html', {'book': book})

    return render(request, 'books/book_delete.html', {'book': book})

@login_required
def borrow_approve(request, pk):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to approve borrows.")
        return redirect('book_list')

    borrow = get_object_or_404(Borrow, pk=pk, status='requested')
    if request.user.is_librarian and not request.user.is_superuser and borrow.centre != request.user.centre:
        messages.error(request, "You can only approve borrows for your own centre.")
        return redirect('book_list')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                if not borrow.book.is_available():
                    messages.error(request, "The book is no longer available.")
                    return redirect('book_list')
                borrow.status = 'issued'
                borrow.issue_date = timezone.now()
                borrow.issued_by = request.user
                borrow.book.update_available_copies()
                borrow.save()
                Notification.objects.create(
                    user=borrow.user,
                    notification_type='borrow_approved',
                    message=f"Your request to borrow '{borrow.book.title}' has been approved.",
                    book=borrow.book,
                    borrow=borrow
                )
                messages.success(request, "Borrow request approved.", extra_tags='green')
                return redirect('book_list')
        except Exception as e:
            messages.error(request, f"Error approving borrow: {str(e)}")
            return render(request, 'books/borrow_approve.html', {'borrow': borrow})

    return render(request, 'books/borrow_approve.html', {'borrow': borrow})

def sample_csv_download(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sample_book_upload.csv"'

    writer = csv.writer(response)
    writer.writerow(['book_title', 'author_name', 'book_code', 'isbn', 'publisher', 'pub_year'])
    writer.writerow([
        'Sample Book Title',
        'John Doe',
        '813.4',
        '9783161484100',
        'Sample Publisher',
        '2023',
    ])

    return response