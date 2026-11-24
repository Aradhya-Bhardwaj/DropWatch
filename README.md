# DropWatch: student dropout analysis for school education

DropWatch shows where and why students drop out of school, across five dimensions (school, area, gender, social category, class and age), and turns the worst groups into scheme recommendations whose effect is measured the following year.

Built with Django only, within the course syllabus: function-based views, `path()` and `re_path()` URLs, Django Template Language with inheritance, Django forms with CSRF and validation, models with foreign keys and migrations, the admin with groups and permissions, sessions, cookies and built-in authentication, and Django's test framework.

## Run it

If your terminal or editor opened in the parent folder, first make sure you are in the directory containing `manage.py`:

```powershell
# Windows (PowerShell):
cd dropwatch                         # only if not already in the folder with manage.py
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
Get-Content scripts\seed_data.py | python manage.py shell   # about 15 seconds
python manage.py runserver
```

```bash
# Linux / macOS (Bash):
cd dropwatch                         # only if not already in the folder with manage.py
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py shell < scripts/seed_data.py               # about 15 seconds
python manage.py runserver
```

Open http://127.0.0.1:8000. If you received the project with `db.sqlite3` already in it, skip `migrate` and the seed step.

### Demo accounts

All passwords are `DropWatch@2026`.

| Username | Role | Sees |
| --- | --- | --- |
| `state_officer` | State education officer | Every district; can approve recommendations |
| `deo_firozpur` | District education officer | Firozpur only |
| `school_head` | School head | One school in Firozpur; can add students, record exits, upload CSVs |
| `admin` | Superuser | Everything, plus `/admin/` |

### Run the tests

```bash
python manage.py test
```

47 tests cover the rate calculations, hotspot detection, URL regular expressions, login and session behaviour, cookies, CSRF, form validation, the CSV import, jurisdiction rules, user management, custom error pages and the recommendation workflow.

## What is in it

| Page | What it shows |
| --- | --- |
| Overview | Headline rates, change since last year, dropout by class and stage, top hotspots, reasons |
| Hotspots | Groups of 30+ students at 1.5× the overall rate or more, with top reasons and matched schemes |
| Attendance watchlist | Students in the current year below 60% attendance for 3 months running |
| By school | Ranked schools, each compared with its block; girls' toilet effect |
| By area | District tiles, district ranking, blocks, rural vs urban over time |
| By gender | Girls vs boys by class, the widest gap, different reasons |
| By social category | General / OBC / SC / ST rates, trend, category × class |
| By class and age | Rate by class, the 5→6, 8→9 and 10→11 transitions, over-age share |
| Compare any two | Any two dimensions as a heat table |
| Recommendations | Proposed → approved → implemented, with action history and measured impact |
| Schemes and rules | The rules that match hotspots to schemes |
| Students | Roll for the current year, add a student, record a dropout or transfer |
| Upload students | CSV import, validated row by row; nothing saves unless every row passes |
| Users | Create accounts with a role, switch accounts off, change your password |
| Data quality | Silent dropouts, zero-dropout schools whose enrolment fell, untraced transfers, missing reasons |
| School page | One school's rate vs its block, history, reasons, class × gender, students to reach |

Every analysis page shares one filter bar (year, district, block, rural/urban, gender, category, stage). Filters are remembered in the session as you move between pages, and every view can be downloaded as CSV.

## How dropout is counted

For a group in a completed school year: students who dropped out ÷ students enrolled × 100. Transfers are left out of both numbers because those children are still studying. Groups under 10 students are hidden so no child can be identified.

## Project structure

```
dropwatch/
├── dropwatch/          settings, root urls (with 403/404/500 handlers)
├── core/               landing, login/logout, users, dashboard, Profile (role + jurisdiction), shortcuts.py (flash messages, paging)
├── schools/            District, Block, School
├── students/           AcademicYear, Student, Enrollment, ExitRecord, AttendanceRecord; forms; CSV upload
├── analytics/          services.py (all calculations), filters.py (GET + session), views
├── interventions/      Scheme, InterventionRule, Recommendation, ActionLog; engine.py (matching + impact)
├── templates/          base.html, base_public.html, partials, one folder per app, error pages
├── static/             css/dropwatch.css, js/charts.js, vendored Chart.js and fonts (works offline)
└── scripts/            seed_data.py (demo data) and shell_practice.py (insert/update/delete), run through the Django shell
```

## Syllabus coverage (INT253: Web Development in Python using Django)

The project uses only what the syllabus teaches. Charts are drawn with Chart.js in the browser; that is JavaScript, not Django.

### Unit I: Introduction to Django (CO1)

| Topic | Where |
| --- | --- |
| Projects and apps, project structure | One project (`dropwatch/`) with five apps: `core`, `schools`, `students`, `analytics`, `interventions` |
| Creating a project and apps | `django-admin startproject dropwatch`, `python manage.py startapp <name>` |
| `django-admin` and `manage.py` commands | `runserver`, `makemigrations`, `migrate`, `shell`, `test`, `check`, `createsuperuser` |
| App structure | Each app has `models.py`, `views.py`, `urls.py`, `forms.py`, `admin.py`, `tests.py`, `migrations/` |
| Settings | `dropwatch/settings.py`: `INSTALLED_APPS`, `TEMPLATES`, `DATABASES`, `STATIC*`, `LOGIN_URL`, session settings |

### Unit II: Views and URLs (CO2)

| Topic | Where |
| --- | --- |
| Function views and view logic | Every `views.py` (about 30 views) |
| Mapping URLs | `dropwatch/urls.py` with `include()`, app `urls.py` with `app_name` namespaces |
| URLs with parameters | `<int:pk>` in `students/urls.py`, `interventions/urls.py`, `core/urls.py` |
| Regular expressions in URLs | `re_path(r"^schools/(?P<udise>\d{11})/$")` and `re_path(r"^export/(?P<dimension>school\|district\|...)\.csv$")` in `analytics/urls.py` |
| HTTP requests | `request.method`, `request.GET`, `request.POST`, `request.FILES`, `request.COOKIES`, `request.session` |
| Requests and responses | `render`, `redirect`, `HttpResponse` (CSV downloads), `HttpResponseNotAllowed` (POST-only views) |
| Error handling | `get_object_or_404`, `Http404`, `PermissionDenied`; custom `handler403/404/500` and `templates/errors/` (run with `DJANGO_DEBUG=0` to see them) |

### Unit III: Templates, debugging and testing (CO3)

| Topic | Where |
| --- | --- |
| Templates and DTL variables | `templates/` folder, 35 templates |
| Template tags | `{% url %}`, `{% csrf_token %}`, `{% include %}`, `{% with %}`, `{% static %}`, built-in filters such as `json_script`, `floatformat`, `date`, `pluralize` |
| for loops and if/else | Every table and list; `{% for %}...{% empty %}`, `{% if %}/{% elif %}/{% else %}` |
| Dynamic templates | Pages built from query results; navigation highlights the current section |
| Template inheritance | `base.html` (signed-in pages) and `base_public.html` (public pages) with `{% block %}`; 26 child templates use `{% extends %}` |
| Debugging | `DEBUG` switch and `LOGGING` in settings; `log.info(...)` in `students/views.py`; `python manage.py check` |
| Testing | 47 tests in the four `tests.py` files, using `TestCase`, `Client`, `override_settings`. Run `python manage.py test` |

### Unit IV: Forms (CO4)

| Topic | Where |
| --- | --- |
| Building forms | `forms.Form` (filter bar, login, upload, user creation, password change) and `forms.ModelForm` (student, exit record) |
| GET and POST | Filter and explore forms use GET (bookmarkable); everything that saves uses POST |
| CSRF | `{% csrf_token %}` in every POST form, including sign-out; a test checks a POST without the token gets 403 |
| POST redirect (PRG) | Every successful POST redirects; a one-time message is carried across the redirect in the session |
| Data validation | `clean_<field>()` and `clean()` methods: UDISE and student ID formats, age vs class, block inside district, transfer needs a school, exit date inside the school year, CSV columns and every CSV row, password rules |

### Unit V: Models, migrations and admin (CO5)

| Topic | Where |
| --- | --- |
| Creating models | 12 models across the apps, with choices, validators and indexes |
| Migrations | `migrations/` folder in each app: `makemigrations`, `migrate` |
| Django shell: insert, update, delete | `scripts/shell_practice.py` (run with `python manage.py shell < scripts/shell_practice.py`); `scripts/seed_data.py` inserts the demo data the same way |
| ORM | `filter`, `exclude`, `get`, `values`, `annotate(Count(...))`, `Q` objects, lookups across relations such as `school__block__district` |
| Foreign keys | `Block → District`, `School → Block`, `Enrollment → Student/School/AcademicYear`, `OneToOneField` for `ExitRecord` and `Profile` |
| Django admin | Every model registered with `list_display`, `list_filter`, `search_fields`, inlines; `/admin/` |
| Groups, users and permissions | Three groups (State officers, District officers, School staff) with model permissions; `@permission_required` on views; `{% if perms.app.codename %}` in templates |
| Database configuration | `DATABASES` in settings: SQLite by default, MySQL or PostgreSQL with `DB_ENGINE` and connection variables |

### Unit VI: Cookies, sessions, users and authentication (CO6)

| Topic | Where |
| --- | --- |
| Cookies | `dw_last_user` prefills the login form; `dw_notice_dismissed` hides the demo banner for a year (`response.set_cookie`, `request.COOKIES`) |
| Sessions | Filter bar remembered across pages, recently viewed schools, one-time flash messages, selected school (`request.session`) |
| Session expiry | "Keep me signed in": `request.session.set_expiry()` two weeks or browser close |
| Creating and managing users | Users page: create a user with a role, group and jurisdiction; switch accounts off and on; change your own password |
| Login and logout URLs | `/login/`, `/logout/` (POST only), `LOGIN_URL` and `LOGIN_REDIRECT_URL` in settings |
| Login in views | `authenticate()` in the login form, `login()` and `logout()` in function views, `?next=` handling, `@login_required` on every private view |

### Practicals

| Practical | Where |
| --- | --- |
| Set up a project, create an app, basic `manage.py` commands | Unit I above |
| Organise the project structure, explore initial settings | Project layout below; `settings.py` |
| Views for displaying content and handling forms | `analytics/views.py` (display), `students/views.py` (forms) |
| Map views to URLs, handle HTTP methods | App `urls.py`; GET/POST branches; POST-only logout, toggle and generate views |
| Templates for pages and components | `templates/`, shared parts in `templates/partials/` |
| Debug with built-in features | `DEBUG` pages, `LOGGING`, `manage.py check` |
| Basic tests | `python manage.py test` (47 tests) |
| Forms for user input | Add student, record exit, upload CSV, add user, change password |
| Validate forms, CSRF protection | Unit IV above |
| Models for data entities | Unit V above |
| Migrations | `makemigrations`, `migrate` |
| Django admin | `/admin/` |
| Session functionality with cookies | Unit VI above |
| User creation, authentication, permissions | Users page, groups, `@permission_required` |
| Login/logout, secured views | `@login_required`, jurisdiction checks returning 403 |

## Data

All student data is synthetic. `scripts/seed_data.py` simulates four school years for 8 districts of Punjab (120 schools, about 26,000 students), with realistic risk factors built in. It also plants data problems for the data-quality page and one past intervention (free bicycles for girls in Bathinda from 2025-26) so the impact view has a result.
