from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from ..models import Student, Centre, CustomUser

def is_authorized(user):
    return user.is_superuser or user.is_librarian

@login_required
def student_add(request):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to student_add")
        return redirect('dashboard')

    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []

    if request.method == 'POST':
        print(f"POST request for student_add by {request.user.email}: {request.POST}")
        if 'name' in request.POST:
            try:
                centre_id = request.POST.get('centre')
                centre = Centre.objects.get(id=centre_id) if centre_id else None
                if request.user.is_librarian and not request.user.is_superuser and centre != request.user.centre:
                    messages.error(request, "You can only add students for your own centre.")
                    print(f"Error: User {request.user.email} attempted to add student to unauthorized centre")
                    return redirect('student_add')

                student = Student(
                    name=request.POST.get('name') or '',
                    child_ID=int(request.POST.get('child_ID')) if request.POST.get('child_ID') and str(request.POST.get('child_ID')).isdigit() else None,
                    school=request.POST.get('school') or '',
                    centre=centre,
                )
                student.full_clean()
                student.save()
                messages.success(request, "Student added successfully.", extra_tags='green')
                print(f"Student added: {student.name or 'Unnamed'} (child_ID: {student.child_ID}) by {request.user.email}")
                return redirect('student_list')
            except IntegrityError:
                messages.error(request, "Child ID already exists.")
                print(f"IntegrityError: child_ID {request.POST.get('child_ID')} already exists")
            except ValueError as ve:
                messages.error(request, f"Invalid data: {str(ve)}")
                print(f"ValueError: Invalid data for student: {str(ve)}")
            except Exception as e:
                messages.error(request, f"Error adding student: {str(e)}")
                print(f"Unexpected error adding student: {str(e)}")
        else:
            messages.error(request, "Invalid form submission. Please provide student details.")
            print("Error: Invalid form submission, missing student details")

    return render(request, 'students/student_add.html', {'centres': centres})

@login_required
def student_list(request):
    if request.user.is_superuser:
        students = Student.objects.all()
    elif request.user.is_librarian and request.user.centre:
        students = Student.objects.filter(centre=request.user.centre)
    else:
        students = Student.objects.none()

    students = students.order_by('name')

    items_per_page = 10
    paginator = Paginator(students, items_per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    print(f"Student list for {request.user.email}: {students.count()} students retrieved")
    return render(request, 'students/student_list.html', {
        'page_obj': page_obj,
        'students': students,
        'centres': Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []
    })

@login_required
def student_update(request, pk):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to student_update")
        return redirect('dashboard')

    student = get_object_or_404(Student, pk=pk)
    if request.user.is_librarian and not request.user.is_superuser and student.centre != request.user.centre:
        messages.error(request, "You can only update students for your own centre.")
        print(f"Error: User {request.user.email} attempted to update student in unauthorized centre")
        return redirect('student_list')

    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []

    if request.method == 'POST':
        print(f"POST request for student_update by {request.user.email}: {request.POST}")
        try:
            centre_id = request.POST.get('centre')
            centre = Centre.objects.get(id=centre_id) if centre_id else None
            if request.user.is_librarian and not request.user.is_superuser and centre != request.user.centre:
                messages.error(request, "You can only update students for your own centre.")
                print(f"Error: User {request.user.email} attempted to update student to unauthorized centre")
                return redirect('student_update', pk=pk)

            student.name = request.POST.get('name', student.name)
            student.child_ID = int(request.POST.get('child_ID')) if request.POST.get('child_ID') and str(request.POST.get('child_ID')).isdigit() else student.child_ID
            student.school = request.POST.get('school', student.school)
            student.centre = centre or student.centre
            student.full_clean()
            student.save()
            messages.success(request, "Student updated successfully.", extra_tags='green')
            print(f"Student updated: {student.name or 'Unnamed'} (child_ID: {student.child_ID}) by {request.user.email}")
            return redirect('student_list')
        except IntegrityError:
            messages.error(request, "Child ID already exists in the centre.")
            print(f"IntegrityError: child_ID {request.POST.get('child_ID')} already exists")
        except ValueError as ve:
            messages.error(request, f"Invalid data: {str(ve)}")
            print(f"ValueError: Invalid data for student: {str(ve)}")
        except Exception as e:
            messages.error(request, f"Error updating student: {str(e)}")
            print(f"Unexpected error updating student: {str(e)}")

    return render(request, 'students/student_update.html', {'student': student, 'centres': centres})

@login_required
def student_delete(request, pk):
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to student_delete")
        return redirect('dashboard')

    student = get_object_or_404(Student, pk=pk)
    if request.user.is_librarian and not request.user.is_superuser and student.centre != request.user.centre:
        messages.error(request, "You can only delete students for your own centre.")
        print(f"Error: User {request.user.email} attempted to delete student in unauthorized centre")
        return redirect('student_list')

    if request.method == 'POST':
        student_name = student.name or 'Unnamed'
        student_id = student.child_ID
        student.delete()
        messages.success(request, "Student deleted successfully.", extra_tags='green')
        print(f"Student deleted: {student_name} (child_ID: {student_id}) by {request.user.email}")
        return redirect('student_list')

    return redirect('student_list')