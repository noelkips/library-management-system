# library_app/management/commands/populate_database.py
from django.core.management.base import BaseCommand
from django.db import transaction
from library_app.models import Centre, School, Grade, Category, Subject


class Command(BaseCommand):
    help = "Populate Centres, Schools, Grades, Categories and Subjects from your data"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Starting database population...")

        # ====================== 1. CENTRES ======================
        centres_data = [
            (1, "Pangani", "CENTRE_1"), (2, "Area 2", "CENTRE_2"), (3, "Bondeni", "CENTRE_3"),
            (4, "Kosovo", "CENTRE_4"), (5, "Gitathuru", "CENTRE_5"), (6, "Mathare North", "CENTRE_6"),
            (7, "Mabatini", "CENTRE_7"), (8, "Madoya", "CENTRE_8"), (9, "Kiamaiko Ngei", "CENTRE_9"),
            (10, "Kariobangi", "CENTRE_10"), (11, "Baba Dogo", "CENTRE_11"), (12, "Korogocho Grogan", "CENTRE_12"),
            (13, "Korogocho B", "CENTRE_13"), (14, "Korogocho Nyayo", "CENTRE_14"), (15, "Pangani HQ", "CENTRE_15"),
            (16, "Ndovoini", "CENTRE_16"), (17, "Joska", "CENTRE_17"), (18, "Sabaki", "CENTRE_18"),
            (19, "Napusimoru", "CENTRE_19"), (20, "Nanaam", "CENTRE_20"), (21, "Napuu", "CENTRE_21"),
            (22, "Turkana", "CENTRE_22"), (23, "Molo Milimani", "CENTRE_23"), (24, "Mitangoni", "CENTRE_24"),
            (25, "Morokani", "CENTRE_25"), (26, "Namarei", "CENTRE_26"), (27, "Olturot", "CENTRE_27"),
            (28, "Nyakach", "CENTRE_28"), (29, "Nyayo", "CENTRE_29"), (30, "Nyeri", "CENTRE_30"),
            (31, "Pangani", "CENTRE_31"), (32, "Shambini", "CENTRE_32"), (33, "Turi High", "CENTRE_33"),
        ]

        for pk, name, code in centres_data:
            Centre.objects.get_or_create(
                pk=pk,
                defaults={'name': name, 'centre_code': code}
            )
        self.stdout.write(self.style.SUCCESS(f"Created {len(centres_data)} Centres"))

        # ====================== 2. SCHOOLS ======================
        schools_data = [
            (1, "Pangani School", 1), (2, "Area 2 School", 2), (3, "Bondeni School", 3),
            (4, "Kosovo School", 4), (5, "Gitathuru School", 5), (6, "Mathare North School", 6),
            (7, "Mabatini School", 7), (8, "Madoya School", 8), (9, "Kiamaiko Ngei School", 9),
            (10, "Kariobangi School", 10), (11, "Baba Dogo School", 11), (12, "Korogocho Grogan School", 12),
            (13, "Korogocho B School", 13), (14, "Korogocho Nyayo School", 14), (15, "Pangani HQ School", 15),
            (16, "Ndovoini School", 16), (17, "Joska School", 17), (18, "Sabaki School", 18),
            (19, "Napusimoru School", 19), (20, "Nanaam School", 20), (21, "Napuu School", 21),
            (22, "Turkana High School", 22), (23, "Molo Milimani School", 23), (24, "Mitangoni School", 24),
            (25, "Morokani School", 25), (26, "Namarei School", 26), (27, "Olturot School", 27),
            (28, "Nyakach School", 28), (29, "Nyayo School", 29), (30, "Nyeri School", 30),
            (31, "Pangani School", 31), (32, "Shambini School", 32), (33, "Turi High School", 33),
            (36, "Pangani School", 1), (30, "Ndovoini High School", 16), (31, "Ndovoini Primary School", 16),
        ]

        for pk, name, centre_id in schools_data:
            centre = Centre.objects.get(pk=centre_id)
            School.objects.get_or_create(
                pk=pk,
                defaults={'name': name, 'centre': centre}
            )
        self.stdout.write(self.style.SUCCESS(f"Created {len(schools_data)} Schools"))

        # ====================== 3. GRADES ======================
        grades = [
            ("Kindergarten", 0), ("Grade 1", 1), ("Grade 2", 2), ("Grade 3", 3),
            ("Grade 4", 4), ("Grade 5", 5), ("Grade 6", 6), ("Grade 7", 7),
            ("Grade 8", 8), ("Grade 9", 9), ("Grade 10", 10), ("Grade 11", 11), ("Grade 12", 12),
        ]
        for name, order in grades:
            Grade.objects.get_or_create(name=name, defaults={'order': order})
        self.stdout.write(self.style.SUCCESS("Created Grades (KG to Grade 12)"))

        # ====================== 4. CATEGORIES ======================
        categories = [
            "Textbook", "Fiction", "Non-Fiction", "Revision", "Reference",
            "Biography", "Science", "History", "Mathematics", "Literature"
        ]
        for name in categories:
            Category.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS(f"Created {len(categories)} Categories"))

        # ====================== 5. SUBJECTS (Realistic per Grade & Category) ======================
        textbook_subjects = ["Mathematics", "English", "Science", "Social Studies", "Kiswahili", "CRE", "IRE", "Hindu RE"]
        revision_subjects = ["Math Revision", "English Revision", "Science Revision", "Kiswahili Revision"]
        fiction_subjects = ["Story Books", "Novels", "Poetry", "Drama"]
        reference_subjects = ["Dictionary", "Atlas", "Encyclopedia"]

        grades_list = Grade.objects.exclude(name="Kindergarten")
        textbook_cat = Category.objects.get(name="Textbook")
        revision_cat = Category.objects.get(name="Revision")
        fiction_cat = Category.objects.get(name="Fiction")
        reference_cat = Category.objects.get(name="Reference")

        created = 0
        for grade in grades_list:
            # Textbooks
            for subj_name in textbook_subjects:
                Subject.objects.get_or_create(name=subj_name, grade=grade, category=textbook_cat)
                created += 1
            # Revision
            for subj_name in revision_subjects:
                Subject.objects.get_or_create(name=subj_name, grade=grade, category=revision_cat)
                created += 1
            # Fiction & Reference (same for all grades)
            for subj_name in fiction_subjects:
                Subject.objects.get_or_create(name=subj_name, grade=grade, category=fiction_cat)
                created += 1
            for subj_name in reference_subjects:
                Subject.objects.get_or_create(name=subj_name, grade=grade, category=reference_cat)
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created} Subjects"))

        self.stdout.write(self.style.SUCCESS("Database population completed successfully!"))