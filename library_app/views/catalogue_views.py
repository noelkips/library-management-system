from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.http import JsonResponse
from ..models import Catalogue, Book, Centre, CustomUser


def is_authorized(user):
    """Check if user is authorized to manage catalogues."""
    return user.is_superuser or user.is_librarian


@login_required
def get_books_by_centre(request):
    """AJAX endpoint to fetch books for a selected centre."""
    centre_id = request.GET.get('centre_id')
    
    if not centre_id:
        return JsonResponse({'error': 'Centre ID is required'}, status=400)
    
    try:
        centre = Centre.objects.get(id=centre_id)
        
        # Check authorization
        if request.user.is_librarian and not request.user.is_superuser and centre != request.user.centre:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        catalogued_books = Catalogue.objects.filter(centre=centre).values_list('book_id', flat=True)
        books = Book.objects.filter(
            centre=centre,
            is_active=True
        ).exclude(
            id__in=catalogued_books
        ).order_by('title').values('id', 'title', 'author', 'book_code', 'category', 'total_copies')
        
        return JsonResponse({
            'books': list(books),
            'centre_name': centre.name
        })
    except Centre.DoesNotExist:
        return JsonResponse({'error': 'Centre not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def catalogue_add(request):
    """Add a new book to the catalogue with shelf number."""
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('book_list')

    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []

    if request.method == 'POST':
        try:
            book_id = request.POST.get('book')
            shelf_number = request.POST.get('shelf_number')
            centre_id = request.POST.get('centre')
            notes = request.POST.get('notes', '')

            if not book_id or not shelf_number:
                messages.error(request, "Please select a book and enter a shelf number.")
                return redirect('catalogue_add')

            book = Book.objects.get(id=book_id)
            centre = Centre.objects.get(id=centre_id) if centre_id else None

            # Check authorization for centre
            if request.user.is_librarian and not request.user.is_superuser and centre != request.user.centre:
                messages.error(request, "You can only add books to your own centre's catalogue.")
                return redirect('catalogue_add')

            existing_shelf = Catalogue.objects.filter(shelf_number=shelf_number, centre=centre, is_active=True).first()
            if existing_shelf:
                messages.error(request, f"Shelf number '{shelf_number}' already exists in this centre. Please use a different shelf number.")
                return redirect('catalogue_add')

            # Check if book already exists in catalogue for this centre
            existing = Catalogue.objects.filter(book=book, centre=centre).first()
            if existing:
                messages.warning(request, f"This book is already catalogued at shelf {existing.shelf_number}. Updating shelf number.")
                existing.shelf_number = shelf_number
                existing.notes = notes
                existing.save(user=request.user)
            else:
                catalogue = Catalogue(
                    book=book,
                    shelf_number=shelf_number,
                    centre=centre or (request.user.centre if request.user.is_librarian else None),
                    added_by=request.user,
                    notes=notes
                )
                catalogue.save(user=request.user)
                messages.success(request, f"Book '{book.title}' added to catalogue at shelf {shelf_number}.")

            return redirect('catalogue_list')

        except Book.DoesNotExist:
            messages.error(request, "Selected book not found.")
        except Centre.DoesNotExist:
            messages.error(request, "Selected centre not found.")
        except Exception as e:
            messages.error(request, f"Error adding book to catalogue: {str(e)}")

    if request.user.is_superuser:
        catalogued_books = Catalogue.objects.values_list('book_id', flat=True)
        books = Book.objects.filter(is_active=True).exclude(id__in=catalogued_books).order_by('title')
    else:
        catalogued_books = Catalogue.objects.filter(centre=request.user.centre).values_list('book_id', flat=True)
        books = Book.objects.filter(
            centre=request.user.centre,
            is_active=True
        ).exclude(id__in=catalogued_books).order_by('title')

    return render(request, 'catalogue/catalogue_add.html', {
        'books': books,
        'centres': centres
    })


@login_required
def catalogue_list(request):
    """List all catalogued books."""
    if request.user.is_superuser:
        catalogues = Catalogue.objects.filter(is_active=True)
    elif request.user.is_librarian and request.user.centre:
        catalogues = Catalogue.objects.filter(centre=request.user.centre, is_active=True)
    else:
        catalogues = Catalogue.objects.none()

    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        catalogues = catalogues.filter(
            Q(book__title__icontains=search_query) |
            Q(book__author__icontains=search_query) |
            Q(shelf_number__icontains=search_query)
        )

    catalogues = catalogues.order_by('shelf_number')

    # Pagination
    items_per_page = 15
    paginator = Paginator(catalogues, items_per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'catalogue/catalogue_list.html', {
        'page_obj': page_obj,
        'catalogues': catalogues,
        'search_query': search_query
    })


@login_required
def catalogue_update(request, pk):
    """Update catalogue entry (shelf number and notes)."""
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('catalogue_list')

    catalogue = get_object_or_404(Catalogue, pk=pk)

    if request.user.is_librarian and not request.user.is_superuser and catalogue.centre != request.user.centre:
        messages.error(request, "You can only update catalogues for your own centre.")
        return redirect('catalogue_list')

    if request.method == 'POST':
        try:
            shelf_number = request.POST.get('shelf_number')
            notes = request.POST.get('notes', '')

            if not shelf_number:
                messages.error(request, "Shelf number is required.")
                return redirect('catalogue_update', pk=pk)

            existing_shelf = Catalogue.objects.filter(
                shelf_number=shelf_number, 
                centre=catalogue.centre, 
                is_active=True
            ).exclude(pk=pk).first()
            if existing_shelf:
                messages.error(request, f"Shelf number '{shelf_number}' already exists in this centre. Please use a different shelf number.")
                return redirect('catalogue_update', pk=pk)

            catalogue.shelf_number = shelf_number
            catalogue.notes = notes
            catalogue.save(user=request.user)
            messages.success(request, "Catalogue entry updated successfully.")
            return redirect('catalogue_list')

        except Exception as e:
            messages.error(request, f"Error updating catalogue: {str(e)}")

    return render(request, 'catalogue/catalogue_update.html', {'catalogue': catalogue})


@login_required
def catalogue_delete(request, pk):
    """Delete a catalogue entry."""
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('catalogue_list')

    catalogue = get_object_or_404(Catalogue, pk=pk)

    if request.user.is_librarian and not request.user.is_superuser and catalogue.centre != request.user.centre:
        messages.error(request, "You can only delete catalogues for your own centre.")
        return redirect('catalogue_list')

    if request.method == 'POST':
        book_title = catalogue.book.title
        catalogue.delete()
        messages.success(request, f"Catalogue entry for '{book_title}' deleted successfully.")
        return redirect('catalogue_list')

    return render(request, 'catalogue/catalogue_delete.html', {'catalogue': catalogue})
