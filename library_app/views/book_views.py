# books/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import csv
import openpyxl
from io import TextIOWrapper
from ..models import Book, Centre, CustomUser

def is_authorized(user):
    return user.is_superuser or user.is_staff


def is_authorized(user):
    return user.is_superuser or user.is_librarian


def is_authorized(user):
    return user.is_superuser or user.is_librarian

def handle_uploaded_file(request, file, user, centre_id):
    header_mapping = {
        'book_title': 'title',
        'author_name': 'author',
        'category': 'category',
        'book_code': 'book_code',
        'publisher': 'publisher',
        'pub_year': 'year_of_publication',
        'total_no': 'total_copies',
        'available_copies': 'available_copies',
    }

    errors = []
    created_count = 0

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

            if 'book_code' not in headers:
                messages.error(request, "CSV file must include 'book_code' column.")
                print(f"Error: CSV file {file.name} missing required column: book_code")
                return

            for row_index, row in enumerate(reader, start=2):
                if not any(row):
                    print(f"Skipping empty row {row_index}")
                    continue
                data = {header_mapping.get(header, header): value.strip() if value else None for header, value in zip(headers, row) if header in header_mapping}
                print(f"Row {row_index} data: {data}")
                if not data.get('book_code'):
                    errors.append(f"Row {row_index}: Missing book_code")
                    print(f"Error in row {row_index}: Missing book_code")
                    continue
                book_instances.append(data)

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

            if 'book_code' not in headers:
                messages.error(request, "Excel file must include 'book_code' column.")
                print(f"Error: Excel file {file.name} missing required column: book_code")
                return

            for row_index, row in enumerate(ws.iter_rows(min_row=2), start=2):
                data = {header_mapping.get(headers[i], headers[i]): cell.value if cell.value else None for i, cell in enumerate(row) if i < len(headers) and headers[i] in header_mapping}
                print(f"Row {row_index} data: {data}")
                if not data.get('book_code'):
                    errors.append(f"Row {row_index}: Missing book_code")
                    print(f"Error in row {row_index}: Missing book_code")
                    continue
                book_instances.append(data)

        else:
            messages.error(request, "Unsupported file format. Only CSV and XLSX are allowed.")
            print(f"Error: Unsupported file format: {file.name}")
            return

        print(f"Parsed {len(book_instances)} book entries from {file.name}")
        for data in book_instances:
            try:
                with transaction.atomic():
                    book = Book(
                        title=data.get('title') or '',
                        author=data.get('author') or '',
                        category=data.get('category') or '',
                        book_code=str(data.get('book_code')),
                        publisher=data.get('publisher') or '',
                        year_of_publication=int(data.get('year_of_publication')) if data.get('year_of_publication') and str(data.get('year_of_publication')).isdigit() else None,
                        total_copies=int(data.get('total_copies')) if data.get('total_copies') and str(data.get('total_copies')).isdigit() else 1,
                        available_copies=int(data.get('total_copies')) if data.get('total_copies') and str(data.get('total_copies')).isdigit() else 1,
                        centre=centre or (user.centre if user.is_librarian and not user.is_superuser else None),
                        added_by=user,
                    )
                    book.full_clean()
                    book.save(user=user)
                    created_count += 1
                    print(f"Saved book: {book.title or 'Untitled'} (Code: {book.book_code})")
            except IntegrityError:
                errors.append(f"Row with book code {data.get('book_code')}: Already exists in centre")
                print(f"IntegrityError for book code {data.get('book_code')}: Already exists")
            except ValueError as ve:
                errors.append(f"Row with book code {data.get('book_code')}: Invalid data ({str(ve)})")
                print(f"ValueError for book code {data.get('book_code')}: {str(ve)}")
            except Exception as e:
                errors.append(f"Row with book code {data.get('book_code')}: Error saving ({str(e)})")
                print(f"Unexpected error for book code {data.get('book_code')}: {str(e)}")

        if created_count > 0:
            messages.success(request, f"{created_count} books imported successfully.", extra_tags='green')
            print(f"Successfully imported {created_count} books")
        if errors:
            messages.error(request, f"Failed to import {len(errors)} rows due to invalid data or duplicate book codes.")
            print(f"Errors encountered: {errors}")
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
        return redirect('books:dashboard')

    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []

    if request.method == 'POST':
        print(f"POST request for book_add by {request.user.email}: {request.POST}, Files: {request.FILES}")
        if 'file' in request.FILES and request.FILES['file']:
            print(f"Handling file upload: {request.FILES['file'].name}")
            handle_uploaded_file(request, request.FILES['file'], request.user, request.POST.get('centre_id'))
            return redirect('books:book_list')
        elif 'file' in request.POST and not request.FILES:
            messages.error(request, "No file was uploaded. Please select a CSV or Excel file.")
            print("Error: No file uploaded in POST request")
        elif 'title' in request.POST:
            try:
                centre_id = request.POST.get('centre')
                centre = Centre.objects.get(id=centre_id) if centre_id else None
                if request.user.is_librarian and not user.is_superuser and centre != request.user.centre:
                    messages.error(request, "You can only add books for your own centre.")
                    print(f"Error: User {request.user.email} attempted to add book to unauthorized centre")
                    return redirect('books:book_add')

                book = Book(
                    title=request.POST.get('title') or '',
                    author=request.POST.get('author') or '',
                    category=request.POST.get('category') or '',
                    book_code=request.POST.get('book_code'),
                    publisher=request.POST.get('publisher') or '',
                    year_of_publication=int(request.POST.get('year_of_publication')) if request.POST.get('year_of_publication') and request.POST.get('year_of_publication').isdigit() else None,
                    total_copies=int(request.POST.get('total_copies')) if request.POST.get('total_copies') and request.POST.get('total_copies').isdigit() else 1,
                    available_copies=int(request.POST.get('available_copies')) if request.POST.get('available_copies') and request.POST.get('available_copies').isdigit() else request.POST.get('total_copies') or 1,
                    centre=centre,
                    added_by=request.user,
                )
                book.full_clean()
                book.save(user=request.user)
                messages.success(request, "Book added successfully.", extra_tags='green')
                print(f"Book added: {book.title or 'Untitled'} (Code: {book.book_code}) by {request.user.email}")
                return redirect('books:book_list')
            except IntegrityError:
                messages.error(request, "Book code already exists in the centre.")
                print(f"IntegrityError: Book code {request.POST.get('book_code')} already exists")
            except ValueError as ve:
                messages.error(request, f"Invalid data: {str(ve)}")
                print(f"ValueError: Invalid data for book: {str(ve)}")
            except Exception as e:
                messages.error(request, f"Error adding book: {str(e)}")
                print(f"Unexpected error adding book: {str(e)}")
        else:
            messages.error(request, "Invalid form submission. Please provide a file or book details.")
            print("Error: Invalid form submission, missing file or book details")

    return render(request, 'books/book_add.html', {'centres': centres})

@login_required
def book_list(request):
    if request.user.is_superuser:
        books = Book.objects.all()
    elif request.user.is_librarian and request.user.centre:
        books = Book.objects.filter(centre=request.user.centre)
    else:
        books = Book.objects.none()

    books = books.order_by('title')

    items_per_page = 10
    paginator = Paginator(books, items_per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    print(f"Book list for {request.user.email}: {books.count()} books retrieved")
    return render(request, 'books/book_list.html', {
        'page_obj': page_obj,
        'books': books,
        'centres': Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []
    })

@login_required
def book_update(request, pk):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('dashboard')

    book = get_object_or_404(Book, pk=pk)
    if request.user.is_staff and not request.user.is_superuser and book.centre != request.user.centre:
        messages.error(request, "You can only update books for your own centre.")
        return redirect('book_list')

    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []

    if request.method == 'POST':
        try:
            centre_id = request.POST.get('centre')
            centre = Centre.objects.get(id=centre_id) if centre_id else None
            if request.user.is_staff and not request.user.is_superuser and centre != request.user.centre:
                messages.error(request, "You can only update books for your own centre.")
                return redirect('book_update', pk=pk)

            book.title = request.POST.get('title', book.title)
            book.author = request.POST.get('author', book.author)
            book.category = request.POST.get('category', book.category)
            book.book_code = request.POST.get('book_code', book.book_code)
            book.publisher = request.POST.get('publisher', book.publisher)
            book.year_of_publication = request.POST.get('year_of_publication', book.year_of_publication)
            book.total_copies = request.POST.get('total_copies', book.total_copies)
            book.available_copies = request.POST.get('available_copies', book.available_copies)
            book.centre = centre or book.centre
            book.save()
            messages.success(request, "Book updated successfully.")
            return redirect('book_list')
        except IntegrityError:
            messages.error(request, "Book code already exists in the centre.")
        except Exception as e:
            messages.error(request, f"Error updating book: {str(e)}")

    return render(request, 'books/book_update.html', {'book': book, 'centres': centres})

@login_required
def book_delete(request, pk):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('dashboard')

    book = get_object_or_404(Book, pk=pk)
    if request.user.is_staff and not request.user.is_superuser and book.centre != request.user.centre:
        messages.error(request, "You can only delete books for your own centre.")
        return redirect('book_list')

    if request.method == 'POST':
        book.delete()
        messages.success(request, "Book deleted successfully.")
        return redirect('book_list')

    return redirect('book_list')