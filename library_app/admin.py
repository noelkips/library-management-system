from django.contrib import admin
from .models import Centre, CustomUser, Book, Student, Catalogue, Category

admin.site.register(Centre)
admin.site.register(CustomUser)
admin.site.register(Student)
admin.site.register(Category)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'book_code', 'centre', 'is_active')
    list_filter = ('centre', 'is_active')
    search_fields = ('title', 'author', 'book_code')
    readonly_fields = ()
    fieldsets = (
    ('Book Information', {
        'fields': ('title', 'author', 'book_code', 'category', 'publisher', 'year_of_publication')
    }),
    ('Location', {
        'fields': ('centre', 'added_by')
    }),
    ('Status', {
        'fields': ('is_active',)
    }),
)



@admin.register(Catalogue)
class CatalogueAdmin(admin.ModelAdmin):
    list_display = ('book', 'shelf_number', 'centre', 'added_by', 'added_date', 'is_active')
    list_filter = ('centre', 'is_active', 'added_date')
    search_fields = ('book__title', 'book__author', 'shelf_number')
    readonly_fields = ('added_date', 'last_updated')
    fieldsets = (
        ('Book Information', {
            'fields': ('book', 'centre')
        }),
        ('Shelf Details', {
            'fields': ('shelf_number', 'notes')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Audit Trail', {
            'fields': ('added_by', 'added_date', 'last_updated'),
            'classes': ('collapse',)
        }),
    )
