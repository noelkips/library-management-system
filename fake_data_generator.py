import random
import string
from datetime import datetime, timedelta
from faker import Faker
import json

fake = Faker()

# Sample data for categories
categories = [
    "Fiction", "Non-Fiction", "Science", "History", "Biography",
    "Fantasy", "Mystery", "Children's", "Education", "Reference"
]

# Sample publishers
publishers = [
    "Penguin Books", "HarperCollins", "Oxford University Press",
    "Random House", "Scholastic", "McGraw-Hill", "Cambridge University Press"
]

# Predefined Centres
centres = [
    {"model": "library_app.centre", "pk": 1, "fields": {"name": "Pangani", "centre_code": "CENTRE_1"}},
    {"model": "library_app.centre", "pk": 2, "fields": {"name": "Area 2", "centre_code": "CENTRE_2"}},
    {"model": "library_app.centre", "pk": 3, "fields": {"name": "Bondeni", "centre_code": "CENTRE_3"}},
    {"model": "library_app.centre", "pk": 4, "fields": {"name": "Kosovo", "centre_code": "CENTRE_4"}},
    {"model": "library_app.centre", "pk": 5, "fields": {"name": "Gitathuru", "centre_code": "CENTRE_5"}},
    {"model": "library_app.centre", "pk": 6, "fields": {"name": "Mathare North", "centre_code": "CENTRE_6"}},
    {"model": "library_app.centre", "pk": 7, "fields": {"name": "Mabatini", "centre_code": "CENTRE_7"}},
    {"model": "library_app.centre", "pk": 8, "fields": {"name": "Madoya", "centre_code": "CENTRE_8"}},
    {"model": "library_app.centre", "pk": 9, "fields": {"name": "Kiamaiko Ngei", "centre_code": "CENTRE_9"}},
    {"model": "library_app.centre", "pk": 10, "fields": {"name": "Kariobangi", "centre_code": "CENTRE_10"}},
    {"model": "library_app.centre", "pk": 11, "fields": {"name": "Baba Dogo", "centre_code": "CENTRE_11"}},
    {"model": "library_app.centre", "pk": 12, "fields": {"name": "Korogocho Grogan", "centre_code": "CENTRE_12"}},
    {"model": "library_app.centre", "pk": 13, "fields": {"name": "Korogocho B", "centre_code": "CENTRE_13"}},
    {"model": "library_app.centre", "pk": 14, "fields": {"name": "Korogocho Nyayo", "centre_code": "CENTRE_14"}},
    {"model": "library_app.centre", "pk": 15, "fields": {"name": "Pangani HQ", "centre_code": "CENTRE_15"}},
    {"model": "library_app.centre", "pk": 16, "fields": {"name": "Ndovoini", "centre_code": "CENTRE_16"}},
    {"model": "library_app.centre", "pk": 17, "fields": {"name": "Joska", "centre_code": "CENTRE_17"}},
    {"model": "library_app.centre", "pk": 18, "fields": {"name": "Sabaki", "centre_code": "CENTRE_18"}},
    {"model": "library_app.centre", "pk": 19, "fields": {"name": "Napuu", "centre_code": "CENTRE_19"}},
    {"model": "library_app.centre", "pk": 20, "fields": {"name": "Napusimoru", "centre_code": "CENTRE_20"}},
    {"model": "library_app.centre", "pk": 21, "fields": {"name": "Kangegetei", "centre_code": "CENTRE_21"}},
    {"model": "library_app.centre", "pk": 22, "fields": {"name": "Turkana High School", "centre_code": "CENTRE_22"}},
    {"model": "library_app.centre", "pk": 23, "fields": {"name": "Lochoredome", "centre_code": "CENTRE_23"}},
    {"model": "library_app.centre", "pk": 24, "fields": {"name": "Nanam", "centre_code": "CENTRE_24"}},
    {"model": "library_app.centre", "pk": 25, "fields": {"name": "Ethiopia", "centre_code": "CENTRE_25"}},
    {"model": "library_app.centre", "pk": 26, "fields": {"name": "Kargi", "centre_code": "CENTRE_26"}},
    {"model": "library_app.centre", "pk": 27, "fields": {"name": "Olturot", "centre_code": "CENTRE_27"}},
    {"model": "library_app.centre", "pk": 28, "fields": {"name": "Namarei", "centre_code": "CENTRE_28"}},
    {"model": "library_app.centre", "pk": 29, "fields": {"name": "Angaza Discovery Camp", "centre_code": "CENTRE_29"}},
    {"model": "library_app.centre", "pk": 30, "fields": {"name": "Molo Milimani", "centre_code": "CENTRE_30"}},
    {"model": "library_app.centre", "pk": 31, "fields": {"name": "Coram Deo - Molo", "centre_code": "CENTRE_31"}},
    {"model": "library_app.centre", "pk": 32, "fields": {"name": "Molo Turi High School", "centre_code": "CENTRE_32"}},
    {"model": "library_app.centre", "pk": 33, "fields": {"name": "MTTI", "centre_code": "CENTRE_33"}},
    {"model": "library_app.centre", "pk": 34, "fields": {"name": "Kibarani", "centre_code": "CENTRE_34"}},
    {"model": "library_app.centre", "pk": 35, "fields": {"name": "Kiwandani", "centre_code": "CENTRE_35"}},
    {"model": "library_app.centre", "pk": 36, "fields": {"name": "Mitangoni", "centre_code": "CENTRE_36"}},
    {"model": "library_app.centre", "pk": 37, "fields": {"name": "Chumani", "centre_code": "CENTRE_37"}},
    {"model": "library_app.centre", "pk": 38, "fields": {"name": "MCL", "centre_code": "CENTRE_38"}},
    {"model": "library_app.centre", "pk": 39, "fields": {"name": "Nyeri", "centre_code": "CENTRE_39"}},
    {"model": "library_app.centre", "pk": 40, "fields": {"name": "Elpida", "centre_code": "CENTRE_40"}},
    {"model": "library_app.centre", "pk": 41, "fields": {"name": "Nyakach", "centre_code": "CENTRE_41"}},
    {"model": "library_app.centre", "pk": 42, "fields": {"name": "Morokani", "centre_code": "CENTRE_42"}},
    {"model": "library_app.centre", "pk": 43, "fields": {"name": "Shambini", "centre_code": "CENTRE_43"}},
    {"model": "library_app.centre", "pk": 44, "fields": {"name": "Kiamaiko Main", "centre_code": "CENTRE_44"}},
    {"model": "library_app.centre", "pk": 45, "fields": {"name": "Kang’agetei", "centre_code": "CENTRE_45"}},
]

# Predefined Schools
schools = [
    {"model": "library_app.school", "pk": 1, "fields": {"name": "Area 2 School", "school_code": "SCHOOL_1", "centre": 2}},
    {"model": "library_app.school", "pk": 2, "fields": {"name": "Babadogo School", "school_code": "SCHOOL_2", "centre": 11}},
    {"model": "library_app.school", "pk": 3, "fields": {"name": "Bondeni School", "school_code": "SCHOOL_3", "centre": 3}},
    {"model": "library_app.school", "pk": 4, "fields": {"name": "Chumani School", "school_code": "SCHOOL_4", "centre": 37}},
    {"model": "library_app.school", "pk": 5, "fields": {"name": "Coram Deo School", "school_code": "SCHOOL_5", "centre": 31}},
    {"model": "library_app.school", "pk": 6, "fields": {"name": "Gitathuru School", "school_code": "SCHOOL_6", "centre": 5}},
    {"model": "library_app.school", "pk": 7, "fields": {"name": "Grogan School", "school_code": "SCHOOL_7", "centre": 12}},
    {"model": "library_app.school", "pk": 8, "fields": {"name": "Joska School", "school_code": "SCHOOL_8", "centre": 17}},
    {"model": "library_app.school", "pk": 9, "fields": {"name": "Mohi Girls High School", "school_code": "SCHOOL_9", "centre": 17}},
    {"model": "library_app.school", "pk": 10, "fields": {"name": "Kang’agetei School", "school_code": "SCHOOL_10", "centre": 45}},
    {"model": "library_app.school", "pk": 11, "fields": {"name": "Kargi School", "school_code": "SCHOOL_11", "centre": 26}},
    {"model": "library_app.school", "pk": 12, "fields": {"name": "Kariobangi School", "school_code": "SCHOOL_12", "centre": 10}},
    {"model": "library_app.school", "pk": 13, "fields": {"name": "Kiamaiko School", "school_code": "SCHOOL_13", "centre": 44}},
    {"model": "library_app.school", "pk": 14, "fields": {"name": "Kiamaiko Ngei School", "school_code": "SCHOOL_14", "centre": 44}},
    {"model": "library_app.school", "pk": 15, "fields": {"name": "Kibarani School", "school_code": "SCHOOL_15", "centre": 34}},
    {"model": "library_app.school", "pk": 16, "fields": {"name": "Kiwandani School", "school_code": "SCHOOL_16", "centre": 35}},
    {"model": "library_app.school", "pk": 17, "fields": {"name": "Korogocho B School", "school_code": "SCHOOL_17", "centre": 13}},
    {"model": "library_app.school", "pk": 18, "fields": {"name": "Kosovo School", "school_code": "SCHOOL_18", "centre": 4}},
    {"model": "library_app.school", "pk": 19, "fields": {"name": "Lochoredome School", "school_code": "SCHOOL_19", "centre": 23}},
    {"model": "library_app.school", "pk": 20, "fields": {"name": "Mabatini School", "school_code": "SCHOOL_20", "centre": 7}},
    {"model": "library_app.school", "pk": 21, "fields": {"name": "Madoya School", "school_code": "SCHOOL_21", "centre": 8}},
    {"model": "library_app.school", "pk": 22, "fields": {"name": "Mathare North School", "school_code": "SCHOOL_22", "centre": 6}},
    {"model": "library_app.school", "pk": 23, "fields": {"name": "Molo Milimani School", "school_code": "SCHOOL_23", "centre": 30}},
    {"model": "library_app.school", "pk": 24, "fields": {"name": "Mitangoni School", "school_code": "SCHOOL_24", "centre": 36}},
    {"model": "library_app.school", "pk": 25, "fields": {"name": "Morokani School", "school_code": "SCHOOL_25", "centre": 42}},
    {"model": "library_app.school", "pk": 26, "fields": {"name": "Namarei School", "school_code": "SCHOOL_26", "centre": 28}},
    {"model": "library_app.school", "pk": 27, "fields": {"name": "Nanaam School", "school_code": "SCHOOL_27", "centre": 24}},
    {"model": "library_app.school", "pk": 28, "fields": {"name": "Napusimoru School", "school_code": "SCHOOL_28", "centre": 20}},
    {"model": "library_app.school", "pk": 29, "fields": {"name": "Napuu School", "school_code": "SCHOOL_29", "centre": 19}},
    {"model": "library_app.school", "pk": 30, "fields": {"name": "Ndovoini High School", "school_code": "SCHOOL_30", "centre": 16}},
    {"model": "library_app.school", "pk": 31, "fields": {"name": "Ndovoini Primary School", "school_code": "SCHOOL_31", "centre": 16}},
    {"model": "library_app.school", "pk": 32, "fields": {"name": "Nyakach School", "school_code": "SCHOOL_32", "centre": 41}},
    {"model": "library_app.school", "pk": 33, "fields": {"name": "Nyayo School", "school_code": "SCHOOL_33", "centre": 14}},
    {"model": "library_app.school", "pk": 34, "fields": {"name": "Nyeri School", "school_code": "SCHOOL_34", "centre": 39}},
    {"model": "library_app.school", "pk": 35, "fields": {"name": "Olturot School", "school_code": "SCHOOL_35", "centre": 27}},
    {"model": "library_app.school", "pk": 36, "fields": {"name": "Pangani School", "school_code": "SCHOOL_36", "centre": 1}},
    {"model": "library_app.school", "pk": 37, "fields": {"name": "Shambini School", "school_code": "SCHOOL_37", "centre": 43}},
    {"model": "library_app.school", "pk": 38, "fields": {"name": "Turi High School", "school_code": "SCHOOL_38", "centre": 32}},
    {"model": "library_app.school", "pk": 39, "fields": {"name": "Turkana High School", "school_code": "SCHOOL_39", "centre": 22}},
]

# Initialize data with centres and schools
data = centres + schools

# Track used values to ensure uniqueness
used_isbns = set()  # For Book.isbn
used_book_code_centre = set()  # For Book unique_together (book_code, centre)
used_child_ids = set()  # For Student.child_ID
used_catalogue_book_centre = set()  # For Catalogue unique_together (book, centre)

# 1. CustomUser (10 users: 2 superusers, 2 librarians, 2 students, 2 teachers, 2 others)
for i in range(1, 11):
    user_fields = {
        "is_superuser": False,
        "is_librarian": False,
        "is_student": False,
        "is_teacher": False,
        "is_other": False,
        "is_staff": False
    }
    # Assign roles to ensure at least 2 of each type
    if i <= 2:
        role = ("is_superuser", True, True)
    elif i <= 4:
        role = ("is_librarian", True, False)
    elif i <= 6:
        role = ("is_student", True, False)
    elif i <= 8:
        role = ("is_teacher", True, False)
    else:
        role = ("is_other", True, False)
    user_fields[role[0]] = role[1]
    user_fields["is_staff"] = role[2] or user_fields["is_superuser"]
    is_active = random.choice([True, False])
    centre_id = random.randint(1, 45)
    email = fake.email()
    while email in [u["fields"]["email"] for u in data if u["model"] == "library_app.CustomUser"]:
        email = fake.email()  # Ensure unique email
    first_name = fake.first_name()
    last_name = fake.last_name()
    data.append({
        "model": "library_app.CustomUser",
        "pk": i,
        "fields": {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "is_active": is_active,
            "force_password_change": random.choice([True, False]),
            "centre": centre_id,
            **user_fields,
            "groups": [],
            "user_permissions": []
        }
    })

# 2. Category (10 categories)
for i in range(11, 21):
    category_name = random.choice(categories)
    categories.remove(category_name)  # Ensure uniqueness
    data.append({
        "model": "library_app.Category",
        "pk": i - 10,
        "fields": {
            "name": category_name,
            "description": fake.sentence()
        }
    })

# 3. Book (20 books)
for i in range(21, 41):
    centre_id = random.randint(1, 45)
    added_by_id = random.randint(1, 10)  # Random existing user
    category_id = random.randint(1, 10)  # Random existing category
    book_code = f"BOOK_{i:04d}_{random.randint(1000, 9999)}"
    # Ensure book_code and centre combination is unique
    attempts = 0
    max_attempts = 100
    while (book_code, centre_id) in used_book_code_centre and attempts < max_attempts:
        book_code = f"BOOK_{i:04d}_{random.randint(1000, 9999)}"
        attempts += 1
    if attempts >= max_attempts:
        print(f"Warning: Could not find unique book_code for centre {centre_id}, using fallback")
        book_code = f"BOOK_{i:04d}_{random.randint(10000, 99999)}"
    used_book_code_centre.add((book_code, centre_id))
    
    # Generate unique ISBN or set to empty string
    isbn = ""
    if random.choice([True, False]):  # 50% chance of assigning an ISBN
        attempts = 0
        while attempts < max_attempts:
            isbn_candidate = f"ISBN-{random.randint(100000000000, 999999999999)}"  # 12-digit range
            if isbn_candidate not in used_isbns:
                isbn = isbn_candidate
                used_isbns.add(isbn)
                break
            attempts += 1
        if attempts >= max_attempts:
            print(f"Warning: Could not generate unique ISBN for book {i}, setting to empty")
            isbn = ""
    
    data.append({
        "model": "library_app.Book",
        "pk": i - 20,
        "fields": {
            "title": fake.sentence(nb_words=4, variable_nb_words=True)[:-1],
            "author": f"{fake.first_name()} {fake.last_name()}",
            "category": category_id,
            "book_code": book_code,
            "isbn": isbn,
            "publisher": random.choice(publishers),
            "year_of_publication": random.randint(2000, 2025),
            "total_copies": random.randint(1, 10),
            "available_copies": random.randint(0, 10),  # Assuming this is an integer
            "centre": centre_id,
            "added_by": added_by_id,
            "is_active": random.choice([True, False])
        }
    })

# 4. Student (5 students, linked to CustomUser where is_student=True)
student_users = [u for u in data if u["model"] == "library_app.CustomUser" and u["fields"]["is_student"]]
if not student_users:
    print("Warning: No students found, skipping Student generation")
else:
    for i, user in enumerate(student_users[:5], start=1):  # Limit to 5 students
        user_id = user["pk"]
        centre_id = user["fields"]["centre"]
        school_ids = [s["pk"] for s in schools if s["fields"]["centre"] == centre_id]
        school_id = random.choice(school_ids) if school_ids else random.randint(1, 39)
        # Generate unique child_ID
        child_id = random.randint(1000, 9999)
        attempts = 0
        max_attempts = 100
        while child_id in used_child_ids and attempts < max_attempts:
            child_id = random.randint(1000, 9999)
            attempts += 1
        if attempts >= max_attempts:
            print(f"Warning: Could not generate unique child_ID for student {i}, using fallback")
            child_id = random.randint(10000, 99999)
        used_child_ids.add(child_id)
        data.append({
            "model": "library_app.Student",
            "pk": i,
            "fields": {
                "child_ID": child_id,
                "name": f"{user['fields']['first_name']} {user['fields']['last_name']}",
                "centre": centre_id,
                "school": school_id,
                "user": user_id,
                "grade": random.choice(['K', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12'])
            }
        })

# 5. Borrow (10 borrows) - Generate before TeacherBookIssue for parent_borrow
borrow_pks = []
for i in range(1, 11):
    user_id = random.randint(1, 10)  # Random existing user
    book_id = random.randint(1, 20)  # Random existing book
    centre_id = random.randint(1, 45)
    issued_by_id = random.randint(1, 10) if random.choice([True, False]) else None
    returned_to_id = random.randint(1, 10) if random.choice([True, False]) else None
    issue_date = fake.date_time_between(start_date="-30d", end_date="now").isoformat() if random.choice([True, False]) else None
    due_date = fake.date_time_between(start_date="+1d", end_date="+30d").isoformat() if random.choice([True, False]) else None
    return_date = fake.date_time_between(start_date="-30d", end_date="now").isoformat() if random.choice([True, False]) else None
    data.append({
        "model": "library_app.Borrow",
        "pk": i,
        "fields": {
            "book": book_id,
            "user": user_id,
            "centre": centre_id,
            "status": random.choice(["requested", "issued", "returned"]),
            "request_date": fake.date_time_between(start_date="-60d", end_date="now").isoformat(),
            "issue_date": issue_date,
            "due_date": due_date,
            "return_date": return_date,
            "renewals": random.randint(0, 2),
            "issued_by": issued_by_id,
            "returned_to": returned_to_id,
            "notes": fake.sentence() if random.choice([True, False]) else ""
        }
    })
    borrow_pks.append(i)

# 6. TeacherBookIssue (10 issues)
teacher_ids = [u["pk"] for u in data if u["model"] == "library_app.CustomUser" and u["fields"]["is_teacher"]]
for i in range(11, 21):
    if not teacher_ids:
        print("Warning: No teachers found, skipping TeacherBookIssue generation")
        continue
    teacher_id = random.choice(teacher_ids)
    book_id = random.randint(1, 20)  # Random existing book
    parent_borrow_id = random.choice(borrow_pks) if borrow_pks else None  # Use existing Borrow pk
    if parent_borrow_id is None:
        print(f"Warning: No borrow records available for TeacherBookIssue {i}, skipping")
        continue
    expected_return_date = fake.date_time_between(start_date="-30d", end_date="+30d").isoformat()
    actual_return_date = fake.date_time_between(start_date="-30d", end_date="+30d").isoformat() if random.choice([True, False]) else None
    data.append({
        "model": "library_app.TeacherBookIssue",
        "pk": i,
        "fields": {
            "parent_borrow": parent_borrow_id,
            "teacher": teacher_id,
            "student_name": f"{fake.first_name()} {fake.last_name()}",
            "student_id": f"STU_{random.randint(1000, 9999)}",
            "book": book_id,
            "status": random.choice(["issued", "returned"]),
            "expected_return_date": expected_return_date,
            "actual_return_date": actual_return_date,
            "notes": fake.sentence() if random.choice([True, False]) else ""
        }
    })

# 7. Reservation (10 reservations)
for i in range(21, 31):
    user_id = random.randint(1, 10)  # Random existing user
    book_id = random.randint(1, 20)  # Random existing book
    centre_id = random.randint(1, 45)
    data.append({
        "model": "library_app.Reservation",
        "pk": i - 20,
        "fields": {
            "book": book_id,
            "user": user_id,
            "centre": centre_id,
            "reservation_date": fake.date_time_between(start_date="-60d", end_date="now").isoformat(),
            "expiry_date": fake.date_time_between(start_date="+1d", end_date="+14d").isoformat(),
            "status": random.choice(["pending", "fulfilled", "cancelled", "expired"]),
            "notified": random.choice([True, False])
        }
    })

# 8. Notification (15 notifications)
for i in range(31, 46):
    user_id = random.randint(1, 10)  # Random existing user
    book_id = random.randint(1, 20) if random.choice([True, False]) else None
    borrow_id = random.randint(1, 10) if random.choice([True, False]) else None
    reservation_id = random.randint(1, 10) if random.choice([True, False]) else None
    data.append({
        "model": "library_app.Notification",
        "pk": i - 30,
        "fields": {
            "user": user_id,
            "notification_type": random.choice([
                "borrow_request", "borrow_approved", "borrow_rejected", "book_issued",
                "book_returned", "book_available", "reservation_fulfilled", "teacher_bulk_request",
                "overdue_reminder"
            ]),
            "message": fake.sentence(),
            "is_read": random.choice([True, False]),
            "created_at": fake.date_time_between(start_date="-60d", end_date="now").isoformat(),
            "book": book_id,
            "borrow": borrow_id,
            "reservation": reservation_id,
            "group_id": f"GROUP_{random.randint(100, 999)}" if random.choice([True, False]) else ""
        }
    })

# 9. Catalogue (20 catalogue entries)
for i in range(46, 66):
    book_id = random.randint(1, 20)  # Random existing book
    centre_id = random.randint(1, 45)
    # Ensure book and centre combination is unique
    attempts = 0
    max_attempts = 100
    while (book_id, centre_id) in used_catalogue_book_centre and attempts < max_attempts:
        book_id = random.randint(1, 20)
        centre_id = random.randint(1, 45)
        attempts += 1
    if attempts >= max_attempts:
        print(f"Warning: Could not find unique book-centre combination for Catalogue {i}, skipping")
        continue
    used_catalogue_book_centre.add((book_id, centre_id))
    added_by_id = random.randint(1, 10)  # Random existing user
    data.append({
        "model": "library_app.Catalogue",
        "pk": i - 45,
        "fields": {
            "book": book_id,
            "shelf_number": f"{random.choice(['A', 'B', 'C'])}{random.randint(1, 10)}",
            "centre": centre_id,
            "added_by": added_by_id,
            "notes": fake.sentence() if random.choice([True, False]) else "",
            "is_active": random.choice([True, False])
        }
    })

# Debugging: Print used ISBNs and other unique fields
print(f"Generated ISBNs: {used_isbns}")
print(f"Generated child_IDs: {used_child_ids}")
print(f"Generated book_code-centre pairs: {used_book_code_centre}")
print(f"Generated catalogue book-centre pairs: {used_catalogue_book_centre}")

# Save to a JSON file
with open('sample_data.json', 'w') as f:
    json.dump(data, f, indent=2)

print("Sample data has been generated and saved to 'sample_data.json'")