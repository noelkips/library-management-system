from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from ..models import Student, Centre, CustomUser, School
import csv
import openpyxl
from io import TextIOWrapper
import random


def is_authorized(user):
    """Check if user has permission to manage students"""
    return user.is_superuser or user.is_librarian


@login_required
def get_schools_by_centre(request):
    """AJAX endpoint to get schools for a specific centre"""
    centre_id = request.GET.get('centre_id')
    if not centre_id:
        return JsonResponse({'schools': []})
    try:
        schools = School.objects.filter(centre_id=centre_id).values('id', 'name')
        return JsonResponse({'schools': list(schools)})
    except Exception as e:
        print(f"Error fetching schools for centre {centre_id}: {str(e)}")
        return JsonResponse({'schools': []}, status=500)

@login_required
def manage_students(request):
    """Main view to list and manage students"""
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to manage_students")
        return redirect('dashboard')

    # Get students based on user role
    if request.user.is_site_admin:
        students = Student.objects.select_related('user', 'centre', 'school').all().order_by('name')
    else:
        students = Student.objects.select_related('user', 'centre', 'school').filter(
            centre=request.user.centre
        ).order_by('name')

    # Search functionality
    query = request.GET.get('q', '').strip()
    if query:
        students = students.filter(
            Q(name__icontains=query) |
            Q(child_ID__icontains=query) |
            Q(school__name__icontains=query)
        )

    # Pagination
    items_per_page_options = [10, 25, 50, 100]
    items_per_page = request.GET.get('items_per_page', '25')
    try:
        items_per_page = int(items_per_page)
        if items_per_page not in items_per_page_options:
            items_per_page = 25
    except ValueError:
        items_per_page = 25

    paginator = Paginator(students, items_per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get schools and centres for dropdowns
    schools = School.objects.filter(centre=request.user.centre)
    centres = Centre.objects.all() if request.user.is_superuser else [request.user.centre] if request.user.centre else []

    # Determine permissions for add/edit/delete
    can_manage = request.user.is_superuser or getattr(request.user, 'is_librarian', False) or getattr(request.user, 'is_site_admin', False)

    context = {
        'students': page_obj,
        'query': query,
        'items_per_page': items_per_page,
        'items_per_page_options': items_per_page_options,
        'schools': schools,
        'centres': centres,
        'grade_choices': Student.GRADE_CHOICES,
        'can_manage': can_manage,  # Pass to template
    }
    return render(request, 'students/student_list.html', context)


@login_required
def add_student(request):
    """Add a single student or handle bulk upload"""
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to add_student")
        return redirect('manage_students')

    if request.method == 'POST':
        # Check if this is a bulk upload
        if 'file' in request.FILES:
            return bulk_upload_students(request)
        
        # Single student add
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        child_ID = request.POST.get('child_ID', '').strip()
        school_id = request.POST.get('school', '').strip()
        grade = request.POST.get('grade', '').strip()
        centre_id = request.POST.get('centre') if request.user.is_superuser else str(request.user.centre.id)
        
        # Validation
        if not all([first_name, child_ID, school_id]):
            messages.error(request, "First name, Child ID, and School are required.")
            return redirect('manage_students')
        
        if Student.objects.filter(child_ID=child_ID).exists():
            messages.error(request, f"Child ID {child_ID} already exists.")
            return redirect('manage_students')
        
        try:
            child_ID = int(child_ID)
            centre = Centre.objects.get(id=centre_id) if request.user.is_superuser else request.user.centre
            school = get_object_or_404(School, id=school_id, centre=centre)
            
            school_code = school.name[:4].upper() if school.name else "SCHL"
            auto_email = f"{school_code}@{child_ID}.libraryhub.com"
            
            with transaction.atomic():
                # Create user with temporary attributes for signal
                user = CustomUser(
                    email=auto_email,
                    first_name=first_name,
                    last_name=last_name,
                    centre=centre,
                    is_student=True,
                    force_password_change=True
                )
                # Set temporary attributes for signal to use
                user._child_ID = child_ID
                user._school_id = school.id
                user.set_password(str(child_ID))
                user.save()
                
                # Update the Student instance created by signal with grade
                student = user.student_profile
                student.grade = grade if grade in dict(Student.GRADE_CHOICES) else None
                student.save()
                
                messages.success(
                    request,
                    f"Student {first_name} {last_name} added successfully! Initial password is their child_ID. They will be forced to change it on first login."
                )
                return redirect('manage_students')
        except ValueError:
            messages.error(request, "Child ID must be a number.")
            return redirect('manage_students')
        except School.DoesNotExist:
            messages.error(request, "Invalid school selection. Please select a valid school.")
            return redirect('manage_students')
        except Exception as e:
            messages.error(request, f"Error creating student: {str(e)}")
            print(f"Unexpected error creating student: {str(e)}")
            return redirect('manage_students')
    
    return redirect('manage_students')


@login_required
def bulk_upload_students(request):
    """Handle bulk upload of students from CSV/Excel file"""
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to bulk_upload_students")
        return redirect('manage_students')

    if request.method != 'POST' or 'file' not in request.FILES:
        messages.error(request, "Please select a file to upload.")
        return redirect('manage_students')
    
    # Get centre and school from form
    school_id = request.POST.get('bulk_school', '').strip()
    centre_id = request.POST.get('bulk_centre', '').strip()
    
    if not school_id:
        messages.error(request, "Please select a school.")
        return redirect('manage_students')
    
    # Determine centre
    if request.user.is_superuser:
        if not centre_id:
            messages.error(request, "Please select a centre.")
            return redirect('manage_students')
        try:
            centre = Centre.objects.get(id=centre_id)
        except Centre.DoesNotExist:
            messages.error(request, "Invalid centre selection.")
            return redirect('manage_students')
    else:
        centre = request.user.centre
    
    # Verify school belongs to centre
    try:
        school = School.objects.get(id=school_id, centre=centre)
    except School.DoesNotExist:
        messages.error(request, "Invalid school selection.")
        return redirect('manage_students')
    
    uploaded_file = request.FILES.get('file')
    if not (uploaded_file.name.endswith('.csv') or uploaded_file.name.endswith('.xlsx')):
        messages.error(request, "Please upload a CSV or Excel file.")
        return redirect('manage_students')
    
    try:
        students_data = []
        errors = []
        
        # Parse file
        if uploaded_file.name.endswith('.csv'):
            text_file = TextIOWrapper(uploaded_file.file, encoding='utf-8')
            reader = csv.DictReader(text_file)
            students_data = list(reader)
        else:
            excel_file = openpyxl.load_workbook(uploaded_file)
            sheet = excel_file.active
            headers = [cell.value for cell in sheet[1]]
            for row in sheet.iter_rows(min_row=2, values_only=True):
                students_data.append(dict(zip(headers, row)))
        
        if not students_data:
            messages.error(request, "The file is empty. Please add student data.")
            return redirect('manage_students')
        
        created_count = 0
        skipped_count = 0
        
        with transaction.atomic():
            for idx, row in enumerate(students_data, start=2):
                row_errors = []
                first_name = str(row.get('first_name', '')).strip()
                last_name = str(row.get('last_name', '')).strip()
                child_ID = str(row.get('child_ID', '')).strip()
                grade = str(row.get('grade', '')).strip()
                
                # Validation
                if not all([first_name, child_ID]):
                    row_errors.append(f"Row {idx}: First name and child_ID are required")
                
                if child_ID and Student.objects.filter(child_ID=child_ID).exists():
                    row_errors.append(f"Row {idx}: child_ID {child_ID} already exists")
                
                if grade and grade not in dict(Student.GRADE_CHOICES):
                    row_errors.append(f"Row {idx}: Invalid grade '{grade}'. Must be one of: {', '.join([g[0] for g in Student.GRADE_CHOICES])}")
                
                if row_errors:
                    errors.extend(row_errors)
                    skipped_count += 1
                    continue
                
                try:
                    child_ID = int(child_ID)
                    
                    school_code = school.name[:4].upper() if school.name else "SCHL"
                    auto_email = f"{school_code}@{child_ID}.libraryhub.com"
                    
                    # Create user
                    user = CustomUser(
                        email=auto_email,
                        first_name=first_name,
                        last_name=last_name,
                        centre=centre,
                        is_student=True,
                        force_password_change=True
                    )
                    user._child_ID = child_ID
                    user._school_id = school.id
                    user.set_password(str(child_ID))
                    user.save()
                    
                    # Update grade on the auto-created student profile
                    student = user.student_profile
                    student.grade = grade if grade else None
                    student.save()
                    
                    created_count += 1
                except ValueError:
                    errors.append(f"Row {idx}: child_ID must be a number")
                    skipped_count += 1
                except Exception as e:
                    errors.append(f"Row {idx}: {str(e)}")
                    skipped_count += 1
        
        # Success message
        if created_count > 0:
            messages.success(
                request,
                f"{created_count} students uploaded successfully to {school.name}! Initial password is their child_ID. They will be forced to change it on first login."
            )
        
        # Error messages
        if errors:
            error_msg = "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more errors"
            messages.error(request, error_msg)
        
        if skipped_count > 0 and created_count == 0:
            messages.warning(request, f"{skipped_count} rows were skipped due to errors.")
    
    except Exception as e:
        messages.error(request, f"Error processing file: {str(e)}")
        print(f"Error in bulk_upload_students: {str(e)}")
    
    return redirect('manage_students')


@login_required
def student_update(request, pk):
    """Update an existing student"""
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to student_update")
        return redirect('dashboard')

    student = get_object_or_404(Student, pk=pk, centre=request.user.centre)

    if request.method == 'POST':
        print(f"POST request for student_update by {request.user.email}: {request.POST}")
        try:
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            child_ID = request.POST.get('child_ID', '').strip()
            school_id = request.POST.get('school', '').strip()
            grade = request.POST.get('grade', '').strip()
            
            # Validation
            if not all([first_name, child_ID, school_id]):
                messages.error(request, "First name, Child ID, and School are required.")
                return redirect('manage_students')
            
            if Student.objects.filter(child_ID=child_ID).exclude(id=student.id).exists():
                messages.error(request, f"Child ID {child_ID} already exists.")
                return redirect('manage_students')
            
            try:
                child_ID = int(child_ID)
                school = get_object_or_404(School, id=school_id, centre=request.user.centre)
                
                with transaction.atomic():
                    # Update user details
                    student.user.first_name = first_name
                    student.user.last_name = last_name
                    
                    # Update email based on school and child_ID
                    school_code = school.name[:4].upper() if school.name else "SCHL"
                    student.user.email = f"{school_code}@{child_ID}.libraryhub.com"
                    student.user.save()
                    
                    # Update student details
                    student.name = f"{first_name} {last_name}".strip()
                    student.child_ID = child_ID
                    student.school = school
                    student.grade = grade if grade in dict(Student.GRADE_CHOICES) else None
                    student.save()
                    
                    messages.success(request, f"Student {student.name} updated successfully!")
                    return redirect('manage_students')
            except ValueError:
                messages.error(request, "Child ID must be a number.")
                return redirect('manage_students')
            except Exception as e:
                messages.error(request, f"Error updating student: {str(e)}")
                print(f"Unexpected error updating student: {str(e)}")
                return redirect('manage_students')
        except Exception as e:
            messages.error(request, f"Error updating student: {str(e)}")
            print(f"Unexpected error updating student: {str(e)}")

    schools = School.objects.filter(centre=request.user.centre)
    context = {
        'student': student,
        'schools': schools,
        'grade_choices': Student.GRADE_CHOICES,
    }
    return render(request, 'students/student_update.html', context)


@login_required
def student_delete(request, pk):
    """Delete a student"""
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to student_delete")
        return redirect('dashboard')

    student = get_object_or_404(Student, pk=pk, centre=request.user.centre)

    if request.method == 'POST':
        student_name = student.name
        user = student.user
        with transaction.atomic():
            student.delete()
            if user:
                user.delete()
        messages.success(request, f"Student {student_name} deleted successfully!")
        return redirect('manage_students')
    
    return redirect('manage_students')


@login_required
def download_sample_excel(request):
    """Download sample Excel template for bulk upload"""
    if not is_authorized(request.user):
        messages.error(request, "You do not have permission to access this page.")
        print(f"Unauthorized access attempt by {request.user.email} to download_sample_excel")
        return redirect('manage_students')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Students"
    
    # Headers (removed school and centre columns)
    headers = ['first_name', 'last_name', 'child_ID', 'grade']
    ws.append(headers)
    
    # Style headers
    from openpyxl.styles import Font, PatternFill, Alignment
    header_fill = PatternFill(start_color="143C50", end_color="143C50", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Sample data
    sample_data = [
        ['John', 'Doe', '1001', 'K'],
        ['Jane', 'Smith', '1002', '1'],
        ['Bob', 'Johnson', '1003', '2'],
    ]
    for row in sample_data:
        ws.append(row)
    
    # Adjust column widths
    ws.column_dimensions['A'].width = 15
    ws.column_dimensions['B'].width = 15
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 12
    
    # Instructions sheet
    instructions_ws = wb.create_sheet("Instructions")
    instructions = [
        ["BULK STUDENT UPLOAD INSTRUCTIONS"],
        [""],
        ["Column Requirements:"],
        ["first_name", "Student's first name (required)"],
        ["last_name", "Student's last name (optional)"],
        ["child_ID", "Unique student ID number (required, must be unique)"],
        ["grade", "Grade level (optional) - Use: K, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12"],
        [""],
        ["Important Notes:"],
        ["- You must select the Centre and School in the upload form"],
        ["- All students in the file will be assigned to the selected school"],
        ["- Email will be auto-generated from school code and child_ID"],
        ["- Initial password will be set to child_ID"],
        ["- Students must change password on first login"],
        ["- Do not modify the header row"],
        ["- Save as .xlsx or .csv format"],
    ]
    for row in instructions:
        instructions_ws.append(row)
    
    instructions_ws.column_dimensions['A'].width = 30
    instructions_ws.column_dimensions['B'].width = 50
    
    # Return file response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="student_upload_template.xlsx"'
    wb.save(response)
    return response