"""
Synthetic demo data for DropWatch.

Run with the Django shell (Unit V: inserting data through the shell):

    python manage.py shell < scripts/seed_data.py

It simulates four school years (2023-24 to 2026-27) for 8 districts of Punjab.
Student records are invented. Risk factors are built in on purpose so the
dashboards show realistic patterns: dropout peaks at the Class 8->9 and
10->11 transitions, is higher for girls in secondary classes, for SC/ST and
below-poverty-line families, for long distances and rural blocks.

It also plants a few problems for the data-quality page (unrecorded reasons,
students who silently disappear, untraced transfers) and one past intervention
(free bicycles for girls in Bathinda from 2025-26) so impact tracking has a result.
"""
import math
import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, Permission, User

from core.models import Profile
from interventions.models import ActionLog, InterventionRule, Recommendation, Scheme
from schools.models import Block, District, School
from students.models import AcademicYear, AttendanceRecord, Enrollment, ExitRecord, Student

rng = random.Random(42)

DISTRICTS = [
    # name, code, risk multiplier, [(block, is_rural)]
    ("Amritsar", "AMR", 1.00, [("Amritsar City", False), ("Ajnala", True), ("Rayya", True)]),
    ("Bathinda", "BTI", 1.25, [("Bathinda City", False), ("Talwandi Sabo", True), ("Rampura Phul", True)]),
    ("Firozpur", "FZR", 1.45, [("Firozpur City", False), ("Zira", True), ("Guru Har Sahai", True)]),
    ("Gurdaspur", "GSP", 1.10, [("Gurdaspur City", False), ("Batala", True), ("Dera Baba Nanak", True)]),
    ("Hoshiarpur", "HSP", 0.95, [("Hoshiarpur City", False), ("Dasuya", True), ("Garhshankar", True)]),
    ("Jalandhar", "JUC", 0.85, [("Jalandhar East", False), ("Nakodar", True), ("Phillaur", True)]),
    ("Kapurthala", "KPT", 0.95, [("Kapurthala City", False), ("Phagwara", True), ("Sultanpur Lodhi", True)]),
    ("Ludhiana", "LDH", 0.80, [("Ludhiana City", False), ("Khanna", True), ("Jagraon", True)]),
]
PLACES = [
    "Nangal Kalan", "Kotli Than Singh", "Bhogpur", "Chak Hakim", "Rurka Kalan", "Bilga", "Talwan", "Mehatpur",
    "Lohian", "Bhullath", "Dhilwan", "Kala Sanghian", "Tanda", "Mukerian", "Hajipur", "Mahilpur", "Saroya",
    "Kathgarh", "Raikot", "Sidhwan Bet", "Doraha", "Machhiwara", "Samrala", "Malaud", "Lopoke", "Chogawan",
    "Jandiala", "Tarsikka", "Mehta", "Baba Bakala", "Goniana", "Bhagta", "Maur", "Sangat", "Nathana", "Bhucho",
    "Makhu", "Mallanwala", "Mamdot", "Talwandi Bhai", "Ferozeshah", "Arifke", "Kalanaur", "Qadian",
    "Fatehgarh Churian", "Dhariwal", "Naushera", "Sri Hargobindpur", "Bhunga", "Bullowal", "Chabbewal",
    "Saila Khurd", "Jaijon", "Kot Fatuhi", "Banga Road", "Dhaliwal", "Kala Bakra", "Lambra", "Adampur", "Alawalpur",
    "Kartarpur", "Shahkot", "Noormahal", "Goraya", "Apra", "Rajgomal", "Khera", "Bhaini", "Ladhowal", "Mullanpur",
    "Dakha", "Halwara", "Sudhar", "Gill", "Kila Raipur", "Bhattian", "Atari", "Kakkar", "Gharinda", "Ramdas",
]
GIRLS = ["Simran", "Harleen", "Jaspreet", "Manpreet", "Navneet", "Gurleen", "Komal", "Pooja", "Sukhmani", "Amandeep",
         "Rajveer", "Kirandeep", "Prabhjot", "Anjali", "Neha", "Sandeep", "Ramandeep", "Gurpreet", "Mehak", "Ishmeet",
         "Tanvi", "Muskan", "Diljot", "Ekam", "Sonia", "Priya", "Jasleen", "Parveen", "Riya", "Seerat"]
BOYS = ["Arjun", "Harpreet", "Gurjot", "Manjot", "Jaskaran", "Karan", "Rohit", "Sahil", "Gagandeep", "Lovepreet",
        "Navjot", "Prabhdeep", "Vikram", "Ajay", "Rajan", "Sukhdeep", "Yuvraj", "Tejinder", "Amrit", "Jashan",
        "Mandeep", "Deepak", "Inderjit", "Kulwinder", "Paramvir", "Arshdeep", "Balraj", "Davinder", "Hardeep", "Ravi"]

YEARS = [("2023-24", 2023, True, 1.08), ("2024-25", 2024, True, 1.00),
         ("2025-26", 2025, True, 0.93), ("2026-27", 2026, False, 1.00)]
# Base yearly probability of dropping out, by class. Peaks at the 8->9 and 10->11 transitions.
BASE = {1: .006, 2: .006, 3: .007, 4: .008, 5: .012, 6: .014, 7: .016, 8: .045,
        9: .055, 10: .075, 11: .05, 12: .03}
MONTHS = [(4, 1), (5, 2), (6, 3), (7, 4), (8, 5), (9, 6), (10, 7)]  # Apr..Oct of the current year


def pick_weighted(pairs):
    total = sum(w for _, w in pairs)
    x = rng.random() * total
    for item, w in pairs:
        x -= w
        if x <= 0:
            return item
    return pairs[-1][0]


def clear():
    for model in (ActionLog, Recommendation, InterventionRule, Scheme, AttendanceRecord, ExitRecord,
                  Enrollment, Student, AcademicYear, Profile, School, Block, District):
        model.objects.all().delete()
    User.objects.filter(username__in=["admin", "state_officer", "deo_firozpur", "school_head"]).delete()


def build_geography():
    schools, place_i = [], 0
    for d_i, (dname, code, dmult, blocks) in enumerate(DISTRICTS, start=1):
        d = District.objects.create(name=dname, code=code)
        d.risk = dmult
        for b_i, (bname, rural) in enumerate(blocks, start=1):
            b = Block.objects.create(name=bname, district=d, is_rural=rural)
            for s_i, stype in enumerate([School.PRIMARY, School.UPPER_PRIMARY, School.SECONDARY,
                                         School.SECONDARY, School.HIGHER_SECONDARY], start=1):
                place = PLACES[place_i % len(PLACES)]
                place_i += 1
                label = {"PRI": "Govt Primary School", "UPR": "Govt Middle School",
                         "SEC": "Govt High School", "HSC": "Govt Senior Secondary School"}[stype]
                mgmt = pick_weighted([("GOVT", 80), ("AIDED", 12), ("PVT", 8)])
                if mgmt != "GOVT":
                    label = label.replace("Govt", "Aided" if mgmt == "AIDED" else "Public")
                s = School.objects.create(
                    udise_code=f"03{d_i:02d}{b_i:02d}{s_i:05d}",
                    name=f"{label}, {place}",
                    block=b, school_type=stype, management=mgmt,
                    area_type="RURAL" if rural else "URBAN",
                    has_girls_toilet=rng.random() > (0.2 if rural else 0.05),
                )
                schools.append(s)
    return schools


def student_risk(st, school, standard, dmult, smult):
    r = dmult * smult
    female = st["gender"] == "F"
    if female and standard >= 8:
        r *= 1.5
    r *= {"GEN": 1.0, "OBC": 1.1, "SC": 1.35, "ST": 1.75}[st["category"]]
    r *= {"BPL": 1.7, "LOW": 1.2, "MID": 0.8}[st["income"]]
    if st["distance"] > 5:
        r *= 1.6 if female else 1.3
    if st["cwsn"]:
        r *= 1.5
    if school.area_type == "RURAL":
        r *= 1.25
    if female and standard >= 6 and not school.has_girls_toilet:
        r *= 1.5
    if st["overage"]:
        r *= 1.3
    return r


def exit_reason(st, school, standard):
    female = st["gender"] == "F"
    options = [("INTEREST", 10), ("FAILED", 12 if standard in (9, 10) else 3), ("HEALTH", 3 + (6 if st["cwsn"] else 0))]
    if st["income"] == "BPL":
        options += [("FINANCIAL", 22), ("LABOUR", 4 if female else 18)]
    else:
        options += [("FINANCIAL", 8), ("LABOUR", 2 if female else 6)]
    if female and standard >= 8:
        options += [("MARRIAGE", 12 if standard >= 9 else 4), ("HOUSEHOLD", 12)]
        if not school.has_girls_toilet:
            options += [("FACILITY", 10)]
    if st["distance"] > 5:
        options += [("DISTANCE", 18 if female else 9)]
    if st["category"] == "ST" or school.block.district.code == "FZR":
        options += [("MIGRATION", 12)]
    if rng.random() < 0.07:  # some schools leave the reason blank
        return "UNKNOWN"
    return pick_weighted(options)


def new_student(school, standard, start_year, seq):
    gender = "F" if rng.random() < 0.48 else "M"
    category = pick_weighted([("SC", 32), ("GEN", 33), ("OBC", 28), ("ST", 7)])
    income = pick_weighted([("BPL", 28 if school.area_type == "RURAL" else 15), ("LOW", 47), ("MID", 25)])
    overage = rng.random() < 0.07
    age = 5 + standard + (rng.randint(1, 3) if overage else 0)
    dob = date(start_year - age, rng.randint(1, 12), rng.randint(1, 28))
    first = rng.choice(GIRLS if gender == "F" else BOYS)
    last = rng.choice(["Kaur", "Rani", "Devi"] if gender == "F" else ["Singh", "Kumar", "Lal"])
    far = school.area_type == "RURAL" and rng.random() < (0.12 + (0.25 if standard >= 9 else 0))
    return {
        "uid": f"PB{seq:010d}", "name": f"{first} {last}", "gender": gender, "category": category,
        "income": income, "dob": dob, "cwsn": rng.random() < 0.025, "overage": overage,
        "distance": round(rng.uniform(5.5, 14) if far else rng.uniform(0.3, 4.5), 1),
        "school": school, "standard": standard,
    }


def simulate(schools):
    years = [AcademicYear.objects.create(label=l, start_year=y, is_complete=c) for l, y, c, _ in YEARS]
    trend = {y.start_year: t for y, (_, _, _, t) in zip(years, YEARS)}
    dmult = {d[1]: d[2] for d in DISTRICTS}
    hard_schools = set(s.pk for s in rng.sample(schools, 9))        # struggling schools
    silent_schools = set(s.pk for s in rng.sample(schools, 3))      # don't report dropouts
    smult = {s.pk: (1.9 if s.pk in hard_schools else rng.uniform(0.8, 1.15)) for s in schools}
    by_block = {}
    for s in schools:
        by_block.setdefault(s.block_id, []).append(s)
    by_district = {}
    for s in schools:
        by_district.setdefault(s.block.district_id, []).append(s)

    seq = 1
    active = []
    for s in schools:
        for std in range(1, s.highest_class + 1):
            size = rng.randint(14, 19) if s.area_type == "RURAL" else rng.randint(17, 23)
            for _ in range(size):
                active.append(new_student(s, std, 2023, seq))
                seq += 1

    student_obj = {}
    for y in years:
        # New Class 1 intake each year after the first
        if y.start_year > 2023:
            for s in schools:
                for _ in range(rng.randint(14, 22)):
                    active.append(new_student(s, 1, y.start_year, seq))
                    seq += 1
        # Create any students not yet in the database
        fresh = [st for st in active if st["uid"] not in student_obj]
        created = Student.objects.bulk_create([
            Student(student_uid=st["uid"], name=st["name"], gender=st["gender"], category=st["category"],
                    date_of_birth=st["dob"], is_cwsn=st["cwsn"], income_band=st["income"],
                    distance_km=Decimal(str(st["distance"])), school=st["school"]) for st in fresh
        ], batch_size=2000)
        for st, obj in zip(fresh, created):
            student_obj[st["uid"]] = obj

        enrollments, outcomes, nxt = [], [], []
        for st in active:
            school, std = st["school"], st["standard"]
            district_code = school.block.district.code
            risk = student_risk(st, school, std, dmult[district_code], smult[school.pk])
            p = BASE[std] * risk * trend[y.start_year]
            # Bicycles for girls in Bathinda from 2025-26 (the planted intervention)
            if district_code == "BTI" and st["gender"] == "F" and std >= 9 and y.start_year >= 2025:
                p *= 0.55
            p = min(p, 0.6)
            att = max(25, min(100, round(rng.gauss(93 - 160 * p, 5))))
            status, reason, to_school = Enrollment.ENROLLED, None, None
            if y.is_complete:
                roll = rng.random()
                if roll < p:
                    status = Enrollment.DROPPED
                    att = max(20, att - rng.randint(8, 20))
                    reason = exit_reason(st, school, std)
                    if school.pk in silent_schools:
                        status, reason = "SILENT", None
                elif roll < p + 0.018 and std < 12:
                    status = Enrollment.TRANSFERRED
                    to_school = rng.choice([s for s in by_district[school.block.district_id]
                                            if s.highest_class >= std + 1 and s.pk != school.pk] or [school])
                elif att < 70 and rng.random() < 0.25 and std not in (12,):
                    status = Enrollment.REPEATED
                elif std == 12:
                    status = Enrollment.COMPLETED
                else:
                    status = Enrollment.PROMOTED
            stored = Enrollment.PROMOTED if status == "SILENT" else status
            enrollments.append(Enrollment(student=student_obj[st["uid"]], school=school, year=y,
                                          standard=std, attendance_pct=att, status=stored))
            outcomes.append((st, status, reason, to_school, p))

            # Work out next year's place
            if not y.is_complete or status in (Enrollment.DROPPED, Enrollment.COMPLETED, "SILENT"):
                continue
            if status == Enrollment.TRANSFERRED:
                if rng.random() < 0.2:      # transfer never shows up at the new school
                    continue
                nxt.append({**st, "school": to_school, "standard": std + 1})
                continue
            new_std = std if status == Enrollment.REPEATED else std + 1
            new_school = school
            if new_std > school.highest_class:
                options = [s for s in by_block[school.block_id] if s.highest_class >= new_std]
                if not options:
                    options = [s for s in by_district[school.block.district_id] if s.highest_class >= new_std]
                new_school = rng.choice(options)
            nxt.append({**st, "school": new_school, "standard": new_std})

        Enrollment.objects.bulk_create(enrollments, batch_size=4000)
        saved = {e.student_id: e for e in Enrollment.objects.filter(year=y)}

        exits, attendance = [], []
        start = date(y.start_year, 4, 1)
        for (st, status, reason, to_school, p) in outcomes:
            e = saved[student_obj[st["uid"]].pk]
            if status == Enrollment.DROPPED:
                exits.append(ExitRecord(enrollment=e, reason=reason, to_school=None,
                                        exit_date=start + timedelta(days=rng.randint(60, 330)),
                                        verified=rng.random() < 0.55))
            elif status == Enrollment.TRANSFERRED:
                exits.append(ExitRecord(enrollment=e, reason="TRANSFER", to_school=to_school,
                                        exit_date=start + timedelta(days=rng.randint(300, 360)),
                                        verified=True))
            if not y.is_complete:
                # Monthly attendance for the year in progress. High-risk students slide downwards.
                sliding = rng.random() < min(0.6, p * 1.6)
                level = rng.gauss(90, 5)
                for month, s_i in MONTHS:
                    if sliding:
                        level -= rng.uniform(4, 8)
                    attendance.append(AttendanceRecord(enrollment=e, month=month, seq=s_i,
                                                       pct=max(5, min(100, round(level + rng.gauss(0, 3))))))
        ExitRecord.objects.bulk_create(exits, batch_size=4000)
        AttendanceRecord.objects.bulk_create(attendance, batch_size=5000)
        print(f"  {y.label}: {len(enrollments):,} enrolments, {sum(1 for o in outcomes if o[1]=='DROPPED'):,} recorded dropouts")
        active = nxt
    return years


def build_schemes():
    S = {}
    def scheme(slug, name, level, cost, desc):
        S[slug] = Scheme.objects.create(slug=slug, name=name, level=level, cost_per_student=cost, description=desc)

    scheme("bicycles-girls", "Free bicycles for girl students", "STATE", 4200,
           "One bicycle per girl who travels more than a few kilometres to a secondary school.")
    scheme("sc-scholarship", "Pre- and post-matric scholarship for SC students", "CENTRAL", 3500,
           "Annual scholarship covering fees and maintenance for Scheduled Caste students.")
    scheme("st-scholarship", "Pre- and post-matric scholarship for ST students", "CENTRAL", 3500,
           "Annual scholarship covering fees and maintenance for Scheduled Tribe students.")
    scheme("kgbv-hostel", "Residential hostel seats for girls (KGBV)", "CENTRAL", 30000,
           "Hostel seats under Samagra Shiksha for girls from disadvantaged groups in Classes 6–12.")
    scheme("transport-allowance", "Transport allowance (Samagra Shiksha)", "CENTRAL", 6000,
           "Escort or transport support for children living far from the nearest school.")
    scheme("girls-toilets", "Separate girls' toilets and sanitary pad provision", "DISTRICT", 900,
           "Infrastructure grant for schools without a working girls' toilet.")
    scheme("remedial", "Remedial classes and board-exam support", "DISTRICT", 1500,
           "After-school remedial teaching for weak learners in Classes 8–10.")
    scheme("outreach-marriage", "Community outreach against early marriage", "DISTRICT", 300,
           "School management committee and panchayat meetings, Beti Bachao Beti Padhao outreach.")
    scheme("seasonal-hostel", "Seasonal hostels for migrant families", "STATE", 12000,
           "Hostel stays so children of seasonal migrants keep studying while families move.")
    scheme("counselling", "Counselling at Class 8 and 10 transitions", "DISTRICT", 400,
           "Career and continuation counselling for students and parents before the stage change.")
    scheme("cash-support", "Conditional cash support for poor households", "STATE", 5000,
           "Monthly support for BPL families, paid while attendance stays above 75%.")
    scheme("bridge-labour", "Labour department follow-up and bridge courses", "STATE", 2500,
           "Identify working children with the labour department and enrol them in bridge courses.")

    R = InterventionRule.objects.create
    R(scheme=S["bicycles-girls"], gender="F", min_standard=8, max_standard=12, reason="DISTANCE", priority=9)
    R(scheme=S["bicycles-girls"], gender="F", min_standard=9, max_standard=12, area_type="RURAL", priority=7)
    R(scheme=S["sc-scholarship"], category="SC", reason="FINANCIAL", priority=9)
    R(scheme=S["sc-scholarship"], category="SC", min_standard=9, priority=6)
    R(scheme=S["st-scholarship"], category="ST", priority=9)
    R(scheme=S["kgbv-hostel"], gender="F", min_standard=6, category="ST", priority=8)
    R(scheme=S["kgbv-hostel"], gender="F", min_standard=6, reason="HOUSEHOLD", priority=6)
    R(scheme=S["transport-allowance"], reason="DISTANCE", priority=7)
    R(scheme=S["girls-toilets"], gender="F", reason="FACILITY", priority=10)
    R(scheme=S["remedial"], min_standard=8, max_standard=10, reason="FAILED", priority=8)
    R(scheme=S["remedial"], reason="INTEREST", priority=5)
    R(scheme=S["outreach-marriage"], gender="F", min_standard=8, reason="MARRIAGE", priority=9)
    R(scheme=S["seasonal-hostel"], reason="MIGRATION", priority=8)
    R(scheme=S["counselling"], min_standard=8, max_standard=10, priority=4)
    R(scheme=S["cash-support"], reason="FINANCIAL", priority=7)
    R(scheme=S["bridge-labour"], reason="LABOUR", priority=8)
    return S


def build_users_and_groups():
    def perms(*codenames):
        return Permission.objects.filter(codename__in=codenames)

    view_all = [f"view_{m}" for m in ("district", "block", "school", "academicyear", "student", "enrollment",
                                      "exitrecord", "attendancerecord", "scheme", "interventionrule",
                                      "recommendation", "actionlog")]
    state, _ = Group.objects.get_or_create(name="State officers")
    state.permissions.set(perms(*view_all, "add_recommendation", "change_recommendation", "add_actionlog",
                                "change_interventionrule", "view_user", "add_user", "change_user"))
    district, _ = Group.objects.get_or_create(name="District officers")
    district.permissions.set(perms(*view_all, "add_recommendation", "change_recommendation", "add_actionlog",
                                   "change_exitrecord"))
    staff, _ = Group.objects.get_or_create(name="School staff")
    staff.permissions.set(perms("view_school", "view_academicyear", "view_student", "view_enrollment",
                                "view_exitrecord", "view_attendancerecord", "add_student", "change_student",
                                "add_enrollment", "change_enrollment", "add_exitrecord", "change_exitrecord"))

    pw = "DropWatch@2026"
    admin = User.objects.create_superuser("admin", "admin@example.com", pw, first_name="Site", last_name="Admin")
    Profile.objects.create(user=admin, role=Profile.STATE)

    so = User.objects.create_user("state_officer", password=pw, first_name="Gurdeep", last_name="Sandhu")
    so.groups.add(state)
    Profile.objects.create(user=so, role=Profile.STATE)

    fzr = District.objects.get(code="FZR")
    deo = User.objects.create_user("deo_firozpur", password=pw, first_name="Harjit", last_name="Brar")
    deo.groups.add(district)
    Profile.objects.create(user=deo, role=Profile.DISTRICT, district=fzr)

    school = School.objects.filter(block__district=fzr, school_type=School.HIGHER_SECONDARY,
                                   area_type="RURAL").first()
    head = User.objects.create_user("school_head", password=pw, first_name="Paramjit", last_name="Kaur")
    head.groups.add(staff)
    Profile.objects.create(user=head, role=Profile.SCHOOL, district=fzr, school=school)
    return so


def plant_past_intervention(S, years, officer):
    """Bathinda started free bicycles for girls in Classes 9-12 in 2025-26, based on 2024-25 rates."""
    y2425 = years[1]
    qs = Enrollment.objects.filter(year=y2425, school__block__district__code="BTI",
                                   student__gender="F", standard__gte=9).exclude(status="TRANSFERRED")
    total = qs.count()
    dropped = qs.filter(status="DROPPED").count()
    rec = Recommendation.objects.create(
        scheme=S["bicycles-girls"], district=District.objects.get(code="BTI"), gender="F",
        min_standard=9, max_standard=12, baseline_year=y2425,
        baseline_rate=Decimal(str(round(100 * dropped / total, 2))), students_in_segment=total,
        status=Recommendation.DONE, started_year=years[2], owner=officer,
    )
    for note, status in [
        ("Hotspot reviewed with the district education office; distance is the top recorded reason.", "APPROVED"),
        ("Bicycles distributed to eligible girls in all three blocks before the 2025-26 session.", "IN_PROGRESS"),
        ("Distribution complete. Track 2025-26 rates against the 2024-25 baseline.", "DONE"),
    ]:
        ActionLog.objects.create(recommendation=rec, user=officer, note=note, status_after=status)


print("Seeding DropWatch demo data (takes about a minute)...")
clear()
all_schools = build_geography()
print(f"  {District.objects.count()} districts, {Block.objects.count()} blocks, {len(all_schools)} schools")
all_years = simulate(all_schools)
schemes = build_schemes()
officer = build_users_and_groups()
plant_past_intervention(schemes, all_years, officer)
print(f"Done. {Student.objects.count():,} students, {Enrollment.objects.count():,} enrolments, "
      f"{AttendanceRecord.objects.count():,} attendance records.")
print("Log in with admin / state_officer / deo_firozpur / school_head, password DropWatch@2026")
