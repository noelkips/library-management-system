# admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Centre, School, Grade, Category, Subject, Book, BookIDSequence,
    CustomUser, Student, Borrow, Reservation, Notification,
    TeacherBookIssue, Catalogue
)


# =============================================================================
# Inline Classes
# =============================================================================
class BorrowInline(admin.TabularInline):
    model = Borrow
    extra = 0
    fields = ('user', 'status', 'request_date', 'issue_date', 'due_date', 'return_date')
    readonly_fields = ('request_date', 'issue_date', 'due_date', 'return_date')
    can_delete = False


class ReservationInline(admin.TabularInline):
    model = Reservation
    extra = 0
    fields = ('user', 'status', 'reservation_date', 'expiry_date')
    readonly_fields = ('reservation_date', 'expiry_date')
    can_delete = False


class CatalogueInline(admin.TabularInline):
    model = Catalogue
    extra = 0
    fields = ('shelf_number', 'centre', 'added_date', 'is_active')
    readonly_fields = ('added_date',)


# =============================================================================
# Custom UserAdmin — Fixed for email-based user (no username field)
# =============================================================================
class CustomUserAdmin(SimpleHistoryAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role_display', 'centre', 'is_active', 'is_staff')
    list_filter = ('is_librarian', 'is_student', 'is_teacher', 'is_site_admin', 'is_staff', 'is_active', 'centre')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    autocomplete_fields = ('centre',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name')}),
        ('Roles', {'fields': ('is_librarian', 'is_student', 'is_teacher', 'is_site_admin', 'is_other')}),
        ('Permissions & Settings', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'centre', 'force_password_change', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
        ('Personal Info', {'fields': ('first_name', 'last_name')}),
        ('Roles', {'fields': ('is_librarian', 'is_student', 'is_teacher', 'is_site_admin', 'centre')}),
    )

    def role_display(self, obj):
        roles = []
        if obj.is_librarian: roles.append("Librarian")
        if obj.is_student: roles.append("Student")
        if obj.is_teacher: roles.append("Teacher")
        if obj.is_site_admin: roles.append("Site Admin")
        if obj.is_other: roles.append("Other")
        return ", ".join(roles) or "User"
    role_display.short_description = 'Role'


# =============================================================================
# Rest of the Admin Classes (Unchanged & Optimized)
# =============================================================================
@admin.register(Centre)
class CentreAdmin(admin.ModelAdmin):
    list_display = ('name', 'centre_code', 'school_count', 'book_count')
    search_fields = ('name', 'centre_code')
    ordering = ('name',)

    def school_count(self, obj):
        return obj.schools.count()
    school_count.short_description = 'Schools'

    def book_count(self, obj):
        return Book.objects.filter(school__centre=obj).count()
    book_count.short_description = 'Books'


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'centre', 'grade_list', 'book_count')
    list_filter = ('centre',)
    search_fields = ('name', 'centre__name')
    autocomplete_fields = ('centre',)

    def grade_list(self, obj):
        grades = obj.active_grades.all().order_by('order')
        return ", ".join([g.name for g in grades]) if grades else "—"
    grade_list.short_description = 'Active Grades'

    def book_count(self, obj):
        return obj.books.count()
    book_count.short_description = 'Books'


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('name', 'order', 'subject_count')
    list_editable = ('order',)
    search_fields = ('name',)
    ordering = ('order', 'name')

    def subject_count(self, obj):
        return obj.subjects.count()
    subject_count.short_description = 'Subjects'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_count')
    search_fields = ('name',)

    def subject_count(self, obj):
        return obj.subjects.count()
    subject_count.short_description = 'Subjects'


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'grade', 'category', 'book_count')
    list_filter = ('category', 'grade')
    search_fields = ('name',)
    autocomplete_fields = ('grade', 'category')

    def book_count(self, obj):
        return obj.books.count()
    book_count.short_description = 'Books'


@admin.register(Book)
class BookAdmin(SimpleHistoryAdmin):
    list_display = (
        'book_id', 'title', 'author', 'subject_display', 'grade_display',
        'school', 'centre', 'isbn', 'is_active', 'is_available'
    )
    list_filter = (
        'is_active', 'available_copies', 'school__centre', 'subject__category',
        'subject__grade', 'year_of_publication'
    )
    search_fields = (
        'title', 'author', 'isbn', 'book_code', 'book_id',
        'subject__name', 'subject__grade__name', 'subject__category__name'
    )
    autocomplete_fields = ('subject', 'school', 'added_by')
    readonly_fields = ('book_id', 'centre')
    inlines = [BorrowInline, ReservationInline, CatalogueInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'author', 'isbn', 'book_code', 'publisher', 'year_of_publication')
        }),
        ('Classification & Location', {
            'fields': ('subject', 'school', 'centre')
        }),
        ('Status', {
            'fields': ('is_active', 'available_copies')
        }),
        ('Metadata', {
            'fields': ('book_id', 'added_by'),
            'classes': ('collapse',)
        }),
    )

    def subject_display(self, obj):
        return str(obj.subject) if obj.subject else "—"
    subject_display.short_description = 'Subject'

    def grade_display(self, obj):
        return obj.subject.grade.name if obj.subject and obj.subject.grade else "—"
    grade_display.short_description = 'Grade'

    def is_available(self, obj):
        status = "Available" if obj.available_copies else "Borrowed"
        color = "green" if obj.available_copies else "red"
        return format_html(f'<span style="color: {color};">{status}</span>')
    is_available.short_description = 'Status'

    def save_model(self, request, obj, form, change):
        if not obj.added_by:
            obj.added_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('name', 'child_ID', 'user_email', 'school', 'grade')
    list_filter = ('school__centre', 'school', 'grade')
    search_fields = ('name', 'child_ID', 'user__email')
    autocomplete_fields = ('user', 'school', 'centre')

    def user_email(self, obj):
        return obj.user.email if obj.user else "—"
    user_email.short_description = 'User Email'


@admin.register(Borrow)
class BorrowAdmin(SimpleHistoryAdmin):
    list_display = ('book', 'user', 'centre', 'status', 'request_date', 'due_date', 'is_overdue')
    list_filter = ('status', 'centre', 'request_date', 'due_date')
    search_fields = ('book__title', 'book__book_id', 'user__email')
    autocomplete_fields = ('book', 'user', 'centre', 'issued_by', 'returned_to')
    readonly_fields = ('request_date',)

    def is_overdue(self, obj):
        if obj.is_overdue():
            return format_html('<span style="color: red;">Overdue</span>')
        return "No"
    is_overdue.short_description = 'Overdue'
    is_overdue.boolean = True


@admin.register(Reservation)
class ReservationAdmin(SimpleHistoryAdmin):
    list_display = ('book', 'user', 'centre', 'status', 'reservation_date', 'expiry_date')
    list_filter = ('status', 'centre', 'reservation_date')
    search_fields = ('book__title', 'user__email')
    autocomplete_fields = ('book', 'user', 'centre')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'message_preview', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    readonly_fields = ('created_at',)

    def message_preview(self, obj):
        return obj.message[:70] + "..." if len(obj.message) > 70 else obj.message
    message_preview.short_description = 'Message'


@admin.register(TeacherBookIssue)
class TeacherBookIssueAdmin(SimpleHistoryAdmin):
    list_display = ('teacher', 'student_name', 'book', 'status', 'issue_date', 'expected_return_date')
    list_filter = ('status', 'issue_date')
    search_fields = ('teacher__email', 'student_name', 'book__title')
    autocomplete_fields = ('teacher', 'book', 'parent_borrow')


@admin.register(Catalogue)
class CatalogueAdmin(admin.ModelAdmin):
    list_display = ('book', 'shelf_number', 'centre', 'added_by', 'added_date')
    list_filter = ('centre', 'added_date')
    search_fields = ('book__title', 'book__book_id', 'shelf_number')
    autocomplete_fields = ('book', 'centre', 'added_by')


@admin.register(BookIDSequence)
class BookIDSequenceAdmin(admin.ModelAdmin):
    list_display = ('centre', 'subject', 'last_number')
    list_filter = ('centre',)
    search_fields = ('centre__name', 'subject__name')

    def has_add_permission(self, request): return request.user.is_superuser
    def has_change_permission(self, request, obj=None): return request.user.is_superuser
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser


# =============================================================================
# Register CustomUser with fixed admin
# =============================================================================
admin.site.register(CustomUser, CustomUserAdmin)