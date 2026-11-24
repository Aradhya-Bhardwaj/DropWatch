"""
Unit V practical: exploring models in the Django shell (insert, query, update, delete).

Run it:       python manage.py shell < scripts/shell_practice.py
Or open the shell with  python manage.py shell  and type the lines one at a time.

It creates a test district, school and student, changes them, then deletes them,
so the demo data is left exactly as it was.
"""
from datetime import date

from django.db.models import Count, Q

from schools.models import Block, District, School
from students.models import AcademicYear, Enrollment, Student

print("\n--- 1. INSERT: create objects (and link them with foreign keys)")
district = District.objects.create(name="Practice District", code="PRC")
block = Block.objects.create(name="Practice Block", district=district, is_rural=True)  # ForeignKey to District
school = School(udise_code="03990100001", name="Govt High School, Practice", block=block, school_type="SEC")
school.save()                                                                            # create() or save()
student = Student.objects.create(student_uid="PB0999999999", name="Test Student", gender="F", category="SC",
                                 date_of_birth=date(2012, 5, 1), school=school)
year = AcademicYear.objects.filter(is_complete=False).first()
enrolment = Enrollment.objects.create(student=student, school=school, year=year, standard=9)
print("Created:", district, "|", school, "|", student, "|", enrolment)

print("\n--- 2. READ: query with the ORM")
print("Schools in Firozpur:", School.objects.filter(block__district__name="Firozpur").count())  # across 2 FKs
print("First 3 girls in Class 9 this year:",
      list(Enrollment.objects.filter(year=year, standard=9, student__gender="F")
           .values_list("student__name", flat=True)[:3]))
print("Get one object:", School.objects.get(udise_code="03990100001"))
print("Reverse foreign key (blocks of a district):", list(district.blocks.all()))
by_status = (Enrollment.objects.filter(year__label="2025-26").values("status")
             .annotate(n=Count("id")).order_by("-n"))
print("Enrolments by status in 2025-26:", {r["status"]: r["n"] for r in by_status})
dropped_girls = Enrollment.objects.filter(Q(year__label="2025-26") & Q(status="DROPPED") & Q(student__gender="F"))
print("Girls who dropped out in 2025-26:", dropped_girls.count())

print("\n--- 3. UPDATE: change one object, then many at once")
student.name = "Test Student Kaur"
student.save()
print("Renamed:", Student.objects.get(pk=student.pk).name)
changed = School.objects.filter(block=block).update(has_girls_toilet=False)
print("Schools updated with .update():", changed, "| toilet now:", School.objects.get(pk=school.pk).has_girls_toilet)

print("\n--- 4. DELETE: remove what we created (CASCADE removes the blocks and enrolments too)")
student.delete()
deleted = district.delete()
print("Deleted:", deleted)
print("Practice district still there?", District.objects.filter(code="PRC").exists())
