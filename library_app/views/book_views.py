from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
import csv
import openpyxl
from io import TextIOWrapper, StringIO
from ..models import Book, Centre, CustomUser, Category

def is_authorized(user):
    return user.is_superuser or user.is_librarian

def handle_uploaded_file(request, file, user, centre_id, category_id):
    header_mapping = {
        'book_title': 'title',
        'author_name': 'author',
        'book_code': 'book_code',
        'isbn': 'isbn',
        'publisher': 'publisher',
        'pub_year': 'year_of_publication',
        'total_no': 'total_copies',
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
                print(f"Selected centre: {centre.name} (ID: {centre_id})")
            except Centre.DoesNotExist:
                messages.error(request, f"Selected centre with ID {centre_id} not found.")
                print(f"Error: Centre ID {centre_id} not found.")
                return

        if user.is_librarian and not user.is_superuser and user.centre and centre != user.centre:
            messages.error(request, "You can only add books for your own centre.")
            print(f"Error: User {user.email} attempted to add books to unauthorized centre {centre.name}.")
            return

        try:
            category = Category.objects.get(id=category_id)
            print(f"Selected category: {category.name} (ID: {category_id})")
        except Category.DoesNotExist:
            messages.error(request, f"Selected category with ID {category_id} not found.")
            print(f"Error: Category ID {category_id} not found.")
            return

        book_instances = []
        if file.name.lower().endswith('.csv'):
            print(f"Processing CSV file: {file.name}")
            file.seek(0)
            decoded_file = TextIOWrapper(file.file, encoding='utf-8-sig')
            reader = csv.reader(decoded_file)
            headers = next(reader, None)
            if not headers:
                messages.error(request, "File is empty or has no headers.")
                print(f"Error: File {file.name} is empty or has no headers.")
                return
            headers = [h.lower().strip() for h in headers]
            print(f"CSV headers: {headers}")

            if 'isbn' not in headers:
                messages.error(request, "CSV file must include 'isbn' column.")
                print(f"Error: CSV file {file.name} missing required column: isbn")
                return

            all_rows = list(reader)
            total_rows = len(all_rows) + 1
            print(f"Total rows in CSV: {total_rows}")

            for row_index, row in enumerate(all_rows, start=2):
                if not any(row):
                    print(f"Skipping empty row {row_index}")
                    skipped_count += 1
                    continue
                data = {header_mapping.get(header, header): value.strip() if value else None for header, value in zip(headers, row) if header in header_mapping}
                print(f"Row {row_index} data: {data}")
                if not data.get('isbn'):
                    errors.append(f"Row {row_index}: Missing ISBN")
                    print(f"Error in row {row_index}: Missing ISBN")
                    continue
                book_instances.append((row_index, data))

        elif file.name.lower().endswith('.xlsx'):
            print(f"Processing Excel file: {file.name}")
            wb = openpyxl.load_workbook(file)
            ws = wb.active
            headers = [cell.value.lower().strip() if cell.value else '' for cell in ws[1]]
            if not headers:
                messages.error(request, "Excel file is empty or has no headers.")
                print(f"Error: Excel file {file.name} is empty or has no headers.")
                return
            print(f"Excel headers: {headers}")

            if 'isbn' not in headers:
                messages.error(request, "Excel file must include 'isbn' column.")
                print(f"Error: Excel file {file.name} missing required column: isbn")
                return

            all_rows = list(ws.iter_rows(min_row=2))
            total_rows = len(all_rows) + 1
            print(f"Total rows in Excel: {total_rows}")

            for row_index, row in enumerate(all_rows, start=2):
                data = {header_mapping.get(headers[i], headers[i]): cell.value if cell.value else None for i, cell in enumerate(row) if i < len(headers) and headers[i] in header_mapping}
                print(f"Row {row_index} data: {data}")
                if not data.get('isbn'):
                    errors.append(f"Row {row_index}: Missing ISBN")
                    print(f"Error in row {row_index}: Missing ISBN")
                    continue
                book_instances.append((row_index, data))

        else:
            messages.error(request, "Unsupported file format. Only CSV and XLSX are allowed.")
            print(f"Error: Unsupported file format: {file.name}")
            return

        print(f"Parsed {len(book_instances)} book entries from {file.name}")
        for row_index, data in book_instances:
            try:
                with transaction.atomic():
                    book = Book(
                        title=data.get('title') or '',
                        author=data.get('author') or '',
                        category=category,
                        book_code=data.get('book_code') or '',
                        isbn=str(data.get('isbn')),
                        publisher=data.get('publisher') or '',
                        year_of_publication=int(data.get('year_of_publication')) if data.get('year_of_publication') and str(data.get('year_of_publication')).isdigit() else None,
                        total_copies=int(data.get('total_copies')) if data.get('total_copies') and str(data.get('total_copies')).isdigit() else 1,
                        available_copies=int(data.get('available_copies') or data.get('total_copies')) if (data.get('available_copies') or data.get('total_copies')) and str(data.get('available_copies') or data.get('total_copies')).isdigit() else 1,
                        centre=centre or (user.centre if user.is_librarian and not user.is_superuser else None),
                        added_by=user,
                    )
                    book.full_clean()
                    book.save()
                    created_count += 1
                    print(f"Saved book: {book.title or 'Untitled'} (ISBN: {book.isbn})")
            except IntegrityError:
                errors.append(f"Row {row_index}: Book with ISBN {data.get('isbn')} already exists")
                print(f"IntegrityError for ISBN {data.get('isbn')} in row {row_index}: Already exists")
            except ValueError as ve:
                errors.append(f"Row {row_index}: Invalid data ({str(ve)})")
                print(f"ValueError for ISBN {data.get('isbn')} in row {row_index}: {str(ve)}")
            except Exception as e:
                errors.append(f"Row {row_index}: Error saving ({str(e)})")
                print(f"Unexpected error for ISBN {data.get('isbn')} in row {row_index}: {str(e)}")

        if created_count > 0:
            messages.success(request, f"{created_count} books imported successfully.", extra_tags='green')
            print(f"Successfully imported {created_count} books")
        if errors:
            messages.error(request, f"Failed to import {len(errors)} rows: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''}")
            print(f"Errors encountered: {errors}")
        messages.info(request, f"Processed {total_rows} rows: {created_count} added, {len(errors)} failed, {skipped_count} skipped.")

        if created_count == 0 and not errors:
            messages.error(request, "No books were imported. Please check the file format and data.")
            print("No books imported from file")

    except Exception as e:
        messages.error(request, f"Error processing file: {str(e)}")
        print(f"Error processing file {file.name}: {str(e)}")

@login_required
def book_add(request):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to book_add")
        return redirect('book_list')

    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []
    categories = Category.objects.all()

    if request.method == 'POST':
        print(f"POST request for book_add by {request.user.email}: {request.POST}, Files: {request.FILES}")
        if 'file' in request.FILES and request.FILES['file']:
            centre_id = request.POST.get('bulk_centre')
            category_id = request.POST.get('bulk_category')
            if not centre_id or not category_id:
                messages.error(request, "Please select both a centre and a category for bulk upload.")
                print(f"Error: Missing centre or category for bulk upload by {request.user.email}")
                return redirect('book_add')
            print(f"Handling file upload: {request.FILES['file'].name}")
            handle_uploaded_file(request, request.FILES['file'], request.user, centre_id, category_id)
            return redirect('book_list')
        elif 'title' in request.POST and request.POST.get('title').strip():
            try:
                centre_id = request.POST.get('centre')
                centre = Centre.objects.get(id=centre_id) if centre_id else None
                if request.user.is_librarian and not request.user.is_superuser and centre != request.user.centre:
                    messages.error(request, "You can only add books for your own centre.")
                    print(f"Error: User {request.user.email} attempted to add book to unauthorized centre")
                    return redirect('book_add')

                category_id = request.POST.get('category')
                try:
                    category = Category.objects.get(id=category_id)
                except Category.DoesNotExist:
                    messages.error(request, "Invalid category selected.")
                    print(f"Error: Invalid category ID {category_id}")
                    return redirect('book_add')

                book = Book(
                    title=request.POST.get('title') or '',
                    author=request.POST.get('author') or '',
                    category=category,
                    book_code=request.POST.get('book_code') or '',
                    isbn=request.POST.get('isbn'),
                    publisher=request.POST.get('publisher') or '',
                    year_of_publication=int(request.POST.get('year_of_publication')) if request.POST.get('year_of_publication') and request.POST.get('year_of_publication').isdigit() else None,
                    total_copies=int(request.POST.get('total_copies')) if request.POST.get('total_copies') and request.POST.get('total_copies').isdigit() else 1,
                    available_copies=int(request.POST.get('available_copies') or request.POST.get('total_copies')) if (request.POST.get('available_copies') or request.POST.get('total_copies')) and (request.POST.get('available_copies') or request.POST.get('total_copies')).isdigit() else 1,
                    centre=centre,
                    added_by=request.user,
                )
                book.full_clean()
                book.save()
                messages.success(request, "Book added successfully.", extra_tags='green')
                print(f"Book added: {book.title or 'Untitled'} (ISBN: {book.isbn}) by {request.user.email}")
                return redirect('book_list')
            except IntegrityError:
                messages.error(request, "Book with this ISBN already exists.")
                print(f"IntegrityError: ISBN {request.POST.get('isbn')} already exists")
            except ValueError as ve:
                messages.error(request, f"Invalid data: {str(ve)}")
                print(f"ValueError: Invalid data for book: {str(ve)}")
            except Exception as e:
                messages.error(request, f"Error adding book: {str(e)}")
                print(f"Unexpected error adding book: {str(e)}")
        else:
            messages.error(request, "Please provide either a file for bulk upload or book details for single book addition.")
            print("Error: Invalid form submission, missing file or book details")

    return render(request, 'books/book_add.html', {'centres': centres, 'categories': categories})

@login_required
def download_sample_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sample_book_upload.csv"'

    writer = csv.writer(response)
    writer.writerow(['book_title', 'author_name', 'book_code', 'isbn', 'publisher', 'pub_year', 'total_no', 'available_copies'])
    writer.writerow([
        'Sample Book Title',
        'John Doe',
        'ABC123',
        '978-3-16-148410-0',
        'Sample Publisher',
        '2023',
        '10',
        '10'
    ])

    return response

@login_required
def book_list(request):
    if request.user.is_superuser:
        books = Book.objects.all()
    elif (request.user.is_librarian or request.user.is_student or request.user.is_teacher)  and request.user.centre:
        books = Book.objects.filter(centre=request.user.centre)
    else:
        books = Book.objects.none()

    query = request.GET.get('q', '')
    category_id = request.GET.get('category', '')
    centre_id = request.GET.get('centre', '')
    available_only = 'available' in request.GET

    if query:
        books = books.filter(
            Q(title__icontains=query) |
            Q(author__icontains=query) |
            Q(book_code__icontains=query) |
            Q(isbn__icontains=query)
        )
    if category_id:
        books = books.filter(category_id=category_id)
    if centre_id and request.user.is_superuser:
        books = books.filter(centre_id=centre_id)
    if available_only:
        books = books.filter(available_copies__gt=0)

    books = books.order_by('title')

    items_per_page = 10
    paginator = Paginator(books, items_per_page)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    print(f"Book list for {request.user.email}: {books.count()} books retrieved")
    return render(request, 'books/book_list.html', {
        'page_obj': page_obj,
        'books': page_obj.object_list,
        'centres': Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else [],
        'categories': Category.objects.all(),
        'query': query,
        'selected_category': category_id,
        'selected_centre': centre_id,
        'available_only': available_only,
    })

@login_required
def book_detail(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.user.is_librarian and not request.user.is_superuser and book.centre != request.user.centre:
        messages.error(request, "You can only view books for your own centre.")
        print(f"Unauthorized access attempt by {request.user.email} to book {book.isbn}")
        return redirect('book_list')

    if request.method == 'POST':
        if not request.user.is_student:
            messages.error(request, "Only students can borrow or reserve books.")
            print(f"Non-student {request.user.email} attempted to borrow/reserve book {book.isbn}")
            return redirect('book_detail', pk=pk)

        action = request.POST.get('action')
        if action == 'borrow' and book.available_copies > 0:
            try:
                with transaction.atomic():
                    book.available_copies -= 1
                    book.save()
                    messages.success(request, "Book borrowed successfully.", extra_tags='green')
                    print(f"Book {book.isbn} borrowed by {request.user.email}")
                    return redirect('book_detail', pk=pk)
            except Exception as e:
                messages.error(request, f"Error borrowing book: {str(e)}")
                print(f"Error borrowing book {book.isbn}: {str(e)}")
        elif action == 'reserve':
            try:
                with transaction.atomic():
                    messages.success(request, "Book reserved successfully.", extra_tags='green')
                    print(f"Book {book.isbn} reserved by {request.user.email}")
                    return redirect('book_detail', pk=pk)
            except Exception as e:
                messages.error(request, f"Error reserving book: {str(e)}")
                print(f"Error reserving book {book.isbn}: {str(e)}")
        else:
            messages.error(request, "Invalid action or book not available.")
            print(f"Invalid action or unavailable book {book.isbn} by {request.user.email}")

    return render(request, 'books/book_detail.html', {
        'book': book,
    })

@login_required
def book_update(request, pk):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to book_update")
        return redirect('book_list')

    book = get_object_or_404(Book, pk=pk)
    if request.user.is_librarian and not request.user.is_superuser and book.centre != request.user.centre:
        messages.error(request, "You can only update books for your own centre.")
        print(f"Unauthorized update attempt by {request.user.email} on book {book.isbn}")
        return redirect('book_list')

    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []
    categories = Category.objects.all()

    if request.method == 'POST':
        try:
            centre_id = request.POST.get('centre')
            centre = Centre.objects.get(id=centre_id) if centre_id else book.centre
            if request.user.is_librarian and not request.user.is_superuser and centre != request.user.centre:
                messages.error(request, "You can only update books for your own centre.")
                print(f"Unauthorized centre update by {request.user.email} on book {book.isbn}")
                return redirect('book_update', pk=pk)

            category_id = request.POST.get('category')
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                messages.error(request, "Invalid category selected.")
                print(f"Error: Invalid category ID {category_id}")
                return redirect('book_update', pk=pk)

            book.title = request.POST.get('title', book.title)
            book.author = request.POST.get('author', book.author)
            book.category = category
            book.book_code = request.POST.get('book_code', book.book_code)
            book.isbn = request.POST.get('isbn', book.isbn)
            book.publisher = request.POST.get('publisher', book.publisher)
            book.year_of_publication = int(request.POST.get('year_of_publication')) if request.POST.get('year_of_publication') and request.POST.get('year_of_publication').isdigit() else book.year_of_publication
            book.total_copies = int(request.POST.get('total_copies')) if request.POST.get('total_copies') and request.POST.get('total_copies').isdigit() else book.total_copies
            book.available_copies = int(request.POST.get('available_copies') or request.POST.get('total_copies')) if (request.POST.get('available_copies') or request.POST.get('total_copies')) and (request.POST.get('available_copies') or request.POST.get('total_copies')).isdigit() else book.available_copies
            book.centre = centre
            book.full_clean()
            book.year_of_publication = request.POST.get('year_of_publication', book.year_of_publication)
            book.total_copies = request.POST.get('total_copies', book.total_copies)
            book.centre = centre or book.centre
            book.save()
            messages.success(request, "Book updated successfully.", extra_tags='green')
            print(f"Book updated: {book.title or 'Untitled'} (ISBN: {book.isbn}) by {request.user.email}")
            return redirect('book_list')
        except IntegrityError:
            messages.error(request, "Book with this ISBN already exists.")
            print(f"IntegrityError: ISBN {request.POST.get('isbn')} already exists")
        except ValueError as ve:
            messages.error(request, f"Invalid data: {str(ve)}")
            print(f"ValueError: Invalid data for book: {str(ve)}")
        except Exception as e:
            messages.error(request, f"Error updating book: {str(e)}")
            print(f"Unexpected error updating book: {str(e)}")

    return render(request, 'books/book_update.html', {'book': book, 'centres': centres, 'categories': categories})

@login_required
def book_delete(request, pk):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to book_delete")
        return redirect('book_list')

    book = get_object_or_404(Book, pk=pk)
    if request.user.is_librarian and not request.user.is_superuser and book.centre != request.user.centre:
        messages.error(request, "You can only delete books for your own centre.")
        print(f"Unauthorized delete attempt by {request.user.email} on book {book.isbn}")
        return redirect('book_list')

    if request.method == 'POST':
        book.delete()
        messages.success(request, "Book deleted successfully.", extra_tags='green')
        print(f"Book deleted: {book.title or 'Untitled'} (ISBN: {book.isbn}) by {request.user.email}")
        return redirect('book_list')

    return render(request, 'books/book_delete.html', {'book': book})
    
