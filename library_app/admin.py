from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
# Only importing the models confirmed in models.py
from .models import Centre, CustomUser, Book, Student, Catalogue, Category, School, Grade, Subject 


@admin.register(CustomUser)
class UserAdmin(BaseUserAdmin):
    # Customize display for CustomUser
    list_display = (
        'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser'
    )
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)

    # Preserve default fieldsets but ensure all CustomUser fields are manageable
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'date_of_birth', 'phone_number')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password', 'password2'),
        }),
    )

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    # FIXED: Replaced 'student_id' with 'child_ID' and added 'grade'
    list_display = ('user_full_name', 'child_ID', 'grade', 'school', 'centre')
    list_filter = ('school', 'school__centre', 'grade')
    # FIXED: Replaced 'student_id' with 'child_ID'
    search_fields = ('child_ID', 'user__email', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user',)
    
    @admin.display(description='User Name')
    def user_full_name(self, obj):
        return obj.user.get_full_name()
    
    @admin.display(description='Centre')
    def centre(self, obj):
        return obj.school.centre if obj.school else 'N/A'
    
    fieldsets = (
        (None, {
            # FIXED: Replaced 'student_id' with 'child_ID' and added 'grade'
            'fields': ('user', 'child_ID', 'school', 'grade')
        }),
    )

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'school_code', 'centre')
    list_filter = ('centre',)
    search_fields = ('name', 'school_code', 'centre__name')


# --- FIXED Grade Model Admin ---

@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    # FIXED: Grade model only has 'name' field
    list_display = ('name',)
    list_filter = () # No fields to filter by
    search_fields = ('name',)
    
    fieldsets = (
        ('Grade Details', {
            'fields': ('name',)
        }),
    )

# --- FIXED Subject Model Admin ---

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    # FIXED: Subject model only has 'name' field
    list_display = ('name',)
    list_filter = () # No fields to filter by
    search_fields = ('name',)
    
    fieldsets = (
        ('Subject Details', {
            'fields': ('name',)
        }),
    )

# --- Updated Book Model Admin to include new fields ---

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    # UPDATED: Added 'grade' and 'subject'
    list_display = ('title', 'author', 'book_code', 'isbn', 'centre', 'category', 'grade', 'subject', 'is_active', 'available_copies')
    # UPDATED: Added 'grade' and 'subject' to filters
    list_filter = ('centre', 'is_active', 'category', 'grade', 'subject')
    search_fields = ('title', 'author', 'book_code', 'isbn')
    readonly_fields = ('available_copies',)
    fieldsets = (
        ('Book Information', {
            # UPDATED: Added 'grade' and 'subject'
            'fields': ('title', 'author', 'book_code', 'isbn', 'category', 'grade', 'subject', 'publisher', 'year_of_publication')
        }),
        ('Stock and Location', {
            'fields': ('centre', 'available_copies')
        }),
        ('Audit and Status', {
            'fields': ('added_by', 'is_active',)
        }),
    )

@admin.register(Catalogue)
class CatalogueAdmin(admin.ModelAdmin):
    list_display = ('book_title', 'shelf_number', 'centre', 'is_active', 'notes', 'added_by', 'added_date')
    list_filter = ('centre', 'is_active', 'added_date')
    search_fields = ('book__title', 'book__author', 'shelf_number', 'notes')
    readonly_fields = ('added_date', 'last_updated')
    raw_id_fields = ('book', 'centre', 'added_by')

    @admin.display(description='Book Title')
    def book_title(self, obj):
        return obj.book.title

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


# Registering simple models without custom Admin classes
admin.site.register(Centre)
admin.site.register(Category)