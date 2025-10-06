"""
TEACHER BOOK ISSUE VIEWS
Allows teachers to manage books they've borrowed from the library
by issuing them to students and tracking returns
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
from datetime import timedelta
from ..models import (
    Book, Borrow, TeacherBookIssue, Notification
)


@login_required
def teacher_my_books(request):
    """Teacher views books they've borrowed from library"""
    if not request.user.is_teacher:
        messages.error(request, "This page is for teachers only.")
        return redirect('book_list')
    
    # Get teacher's active borrows from library
    active_borrows = Borrow.objects.filter(
        user=request.user,
        status='issued'
    ).select_related('book', 'book__category').annotate(
        issued_count=Count('teacher_issues', filter=Q(teacher_issues__status='issued'))
    ).order_by('-issue_date')
    
    context = {
        'active_borrows': active_borrows,
    }
    return render(request, 'teacher_issues/teacher_my_books.html', context)


@login_required
def teacher_issue_to_student(request, borrow_id):
    """Teacher issues a book to a student"""
    if not request.user.is_teacher:
        messages.error(request, "This page is for teachers only.")
        return redirect('book_list')
    
    # Get the parent borrow (teacher's library borrow)
    parent_borrow = get_object_or_404(
        Borrow, 
        pk=borrow_id, 
        user=request.user,
        status='issued'
    )
    
    if request.method == 'POST':
        student_name = request.POST.get('student_name', '').strip()
        student_id = request.POST.get('student_id', '').strip()
        expected_days = request.POST.get('expected_days', '7').strip()
        notes = request.POST.get('notes', '').strip()
        
        if not student_name:
            messages.error(request, "Student name is required.")
            return redirect('teacher_issue_to_student', borrow_id=borrow_id)
        
        try:
            days = int(expected_days)
            expected_return = timezone.now() + timedelta(days=days)
        except ValueError:
            expected_return = timezone.now() + timedelta(days=7)
        
        # Create teacher issue
        teacher_issue = TeacherBookIssue.objects.create(
            parent_borrow=parent_borrow,
            teacher=request.user,
            student_name=student_name,
            student_id=student_id,
            book=parent_borrow.book,
            status='issued',
            expected_return_date=expected_return,
            notes=notes
        )
        teacher_issue.save(user=request.user)
        
        messages.success(request, f"Book '{parent_borrow.book.title}' issued to {student_name}!")
        return redirect('teacher_manage_book', borrow_id=borrow_id)
    
    context = {
        'parent_borrow': parent_borrow,
    }
    return render(request, 'teacher_issues/teacher_issue_to_student.html', context)


@login_required
def teacher_manage_book(request, borrow_id):
    """Teacher manages a specific book and sees all student issues"""
    if not request.user.is_teacher:
        messages.error(request, "This page is for teachers only.")
        return redirect('book_list')
    
    # Get the parent borrow
    parent_borrow = get_object_or_404(
        Borrow, 
        pk=borrow_id, 
        user=request.user,
        status='issued'
    )
    
    # Get all issues for this borrow
    student_issues = TeacherBookIssue.objects.filter(
        parent_borrow=parent_borrow
    ).order_by('-issue_date')
    
    # Separate active and returned
    active_issues = student_issues.filter(status='issued')
    returned_issues = student_issues.filter(status='returned')
    
    context = {
        'parent_borrow': parent_borrow,
        'active_issues': active_issues,
        'returned_issues': returned_issues,
    }
    return render(request, 'teacher_issues/teacher_manage_book.html', context)


@login_required
def teacher_receive_return(request, issue_id):
    """Teacher receives a book back from student"""
    if not request.user.is_teacher:
        messages.error(request, "This page is for teachers only.")
        return redirect('book_list')
    
    issue = get_object_or_404(
        TeacherBookIssue, 
        pk=issue_id, 
        teacher=request.user
    )
    
    if issue.status != 'issued':
        messages.error(request, "This book has already been returned.")
        return redirect('teacher_manage_book', borrow_id=issue.parent_borrow.id)
    
    if request.method == 'POST':
        issue.status = 'returned'
        issue.actual_return_date = timezone.now()
        issue.save(user=request.user)
        
        messages.success(request, f"Book returned by {issue.student_name}!")
        return redirect('teacher_manage_book', borrow_id=issue.parent_borrow.id)
    
    context = {'issue': issue}
    return render(request, 'teacher_issues/teacher_receive_return.html', context)


@login_required
def teacher_all_issues(request):
    """Teacher views all their student issues across all books"""
    if not request.user.is_teacher:
        messages.error(request, "This page is for teachers only.")
        return redirect('book_list')
    
    # Get all issues by this teacher
    issues = TeacherBookIssue.objects.filter(
        teacher=request.user
    ).select_related('book', 'parent_borrow', 'book__category').order_by('-issue_date')
    
    # Search
    search = request.GET.get('search', '')
    if search:
        issues = issues.filter(
            Q(student_name__icontains=search) |
            Q(student_id__icontains=search) |
            Q(book__title__icontains=search)
        )
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        issues = issues.filter(status=status)
    
    # Pagination
    paginator = Paginator(issues, 20)
    page_number = request.GET.get('page')
    issues_page = paginator.get_page(page_number)
    
    context = {
        'issues': issues_page,
        'search': search,
        'status_filter': status,
    }
    return render(request, 'teacher_issues/teacher_all_issues.html', context)


@login_required
def teacher_issue_update(request, issue_id):
    """Teacher updates issue details (e.g., extend expected return date)"""
    if not request.user.is_teacher:
        messages.error(request, "This page is for teachers only.")
        return redirect('book_list')
    
    issue = get_object_or_404(
        TeacherBookIssue, 
        pk=issue_id, 
        teacher=request.user
    )
    
    if request.method == 'POST':
        issue.student_name = request.POST.get('student_name', issue.student_name).strip()
        issue.student_id = request.POST.get('student_id', issue.student_id).strip()
        issue.notes = request.POST.get('notes', issue.notes).strip()
        
        # Update expected return date
        expected_days = request.POST.get('expected_days', '')
        if expected_days:
            try:
                days = int(expected_days)
                issue.expected_return_date = timezone.now() + timedelta(days=days)
            except ValueError:
                pass
        
        issue.save(user=request.user)
        messages.success(request, "Issue updated successfully!")
        return redirect('teacher_manage_book', borrow_id=issue.parent_borrow.id)
    
    context = {'issue': issue}
    return render(request, 'teacher_issues/teacher_issue_update.html', context)