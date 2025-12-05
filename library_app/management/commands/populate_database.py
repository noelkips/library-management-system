# library_app/management/commands/populate_database.py
from django.core.management.base import BaseCommand
from django.db import transaction
from library_app.models import Centre, School, Grade, Category, Subject, Student, CustomUser
from django.contrib.auth.hashers import make_password
import random


class Command(BaseCommand):
    help = "Populate test data — ALL schools have ALL grades & subjects"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Starting FINAL population — ALL SCHOOLS HAVE ALL GRADES...")

        # 1. CENTRES
        centres_data = [
            ("Pangani", "CENTRE_1"), ("Area 2", "CENTRE_2"), ("Bondeni", "CENTRE_3"),
            ("Kosovo", "CENTRE_4"), ("Gitathuru", "CENTRE_5"), ("Mathare North", "CENTRE_6"),
            ("Mabatini", "CENTRE_7"), ("Madoya", "CENTRE_8"), ("Kiamaiko Ngei", "CENTRE_9"),
            ("Kariobangi", "CENTRE_10"), ("Baba Dogo", "CENTRE_11"), ("Korogocho Grogan", "CENTRE_12"),
            ("Korogocho B", "CENTRE_13"), ("Korogocho Nyayo", "CENTRE_14"), ("Pangani HQ", "CENTRE_15"),
            ("Ndovoini", "CENTRE_16"), ("Joska", "CENTRE_17"), ("Sabaki", "CENTRE_18"),
            ("Napusimoru", "CENTRE_19"), ("Nanaam", "CENTRE_20"), ("Napuu", "CENTRE_21"),
            ("Turkana", "CENTRE_22"), ("Molo Milimani", "CENTRE_23"), ("Mitangoni", "CENTRE_24"),
            ("Morokani", "CENTRE_25"), ("Namarei", "CENTRE_26"), ("Olturot", "CENTRE_27"),
            ("Nyakach", "CENTRE_28"), ("Nyayo", "CENTRE_29"), ("Nyeri", "CENTRE_30"),
            ("Shambini", "CENTRE_32"), ("Turi High", "CENTRE_33"),
        ]

        centres = []
        for name, code in centres_data:
            centre, _ = Centre.objects.get_or_create(centre_code=code, defaults={'name': name})
            centres.append(centre)

        # 2. SCHOOLS — 2 per centre
        schools = []
        for centre in centres:
            for suffix in ["Primary School", "High School"]:
                name = f"{centre.name} {suffix}"
                school, _ = School.objects.get_or_create(name=name, defaults={'centre': centre})
                schools.append(school)

        # CRITICAL: ALL SCHOOLS HAVE ALL GRADES
        all_grades = Grade.objects.all()
        for school in schools:
            school.active_grades.set(all_grades)

        self.stdout.write(self.style.SUCCESS(f"Created {len(schools)} Schools — ALL have ALL grades"))

        # 3. GRADES
        for name, order in [
            ("Kindergarten", 0), ("Grade 1", 1), ("Grade 2", 2), ("Grade 3", 3),
            ("Grade 4", 4), ("Grade 5", 5), ("Grade 6", 6), ("Grade 7", 7),
            ("Grade 8", 8), ("Grade 9", 9), ("Grade 10", 10), ("Grade 11", 11), ("Grade 12", 12),
        ]:
            Grade.objects.get_or_create(name=name, defaults={'order': order})

        # 4. CATEGORIES
        categories = {}
        for name in ["Textbook", "Fiction", "Non-Fiction", "Revision", "Reference",
                     "Biography", "Science", "History", "Mathematics", "Literature"]:
            cat, _ = Category.objects.get_or_create(name=name)
            categories[name] = cat

        # 5. SUBJECTS — GLOBAL (same for all schools)
        textbook_cat = categories["Textbook"]
        textbook_names = ["Mathematics", "English", "Science", "Kiswahili", "Social Studies", "CRE", "IRE", "Life Skills"]
        grades = Grade.objects.exclude(name="Kindergarten")

        for grade in grades:
            for name in textbook_names:
                Subject.objects.get_or_create(name=name, grade=grade, category=textbook_cat)

        Subject.objects.get_or_create(name="Story Books", defaults={'grade': None, 'category': categories["Fiction"]})
        Subject.objects.get_or_create(name="Dictionary", defaults={'grade': None, 'category': categories["Reference"]})

        self.stdout.write(self.style.SUCCESS("Subjects ready — shared across all schools"))

        # 6. TEST STUDENTS — 50 safe IDs
        first_names = ["John", "Mary", "James", "Amina", "Peter", "Fatuma", "David", "Grace", "Joseph", "Rose"]
        last_names = ["Kamau", "Wanjiku", "Otieno", "Achieng", "Omondi", "Chebet", "Kiprop", "Njoroge", "Wambui", "Mwangi"]

        created = 0
        for i in range(900000, 900050):
            child_id = str(i)
            if Student.objects.filter(child_ID=child_id).exists():
                continue

            school = random.choice(schools)
            first = random.choice(first_names)
            last = random.choice(last_names)

            try:
                student = Student(
                    child_ID=child_id,
                    name=f"{first} {last}",
                    centre=school.centre,
                    school=school,
                    grade=random.choice([g[0] for g in Student.GRADE_CHOICES[1:]])
                )
                student.save()

                student.user.set_password("1234")
                student.user.force_password_change = True
                student.user.save()
                created += 1
            except:
                pass

        # 7. FINALIZE
        CustomUser.objects.exclude(is_superuser=True).update(
            password=make_password("1234"),
            force_password_change=True
        )

        self.stdout.write(self.style.SUCCESS("POPULATION 100% COMPLETE!"))
        self.stdout.write(self.style.SUCCESS(f"   • {len(centres)} Centres"))
        self.stdout.write(self.style.SUCCESS(f"   • {len(schools)} Schools (all have all grades)"))
        self.stdout.write(self.style.SUCCESS(f"   • {created} Test Students"))
        self.stdout.write(self.style.SUCCESS("   • Login: Child ID (e.g. 900001), Password: 1234"))