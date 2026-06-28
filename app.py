import os
import secrets
from datetime import datetime, timedelta, date
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, abort, session)
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
from urllib.parse import urlparse, urljoin

# ── App config ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'antalya-tours-dev-secret-2026')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'

LANGUAGES = ['Italian', 'English', 'Spanish', 'Portuguese', 'German']
THEMES = ['Food Tour', 'Historical', 'Recreational Activity']
DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
DAY_NUM = {d: i for i, d in enumerate(DAYS_OF_WEEK)}
DATABASE = os.path.join(BASE_DIR, 'antalya_tours.db')

SCHEDULE_TERMS = {
    'English': {
        'every': 'Every',
        'at': 'at',
        'days': {
            'Monday': 'Monday', 'Tuesday': 'Tuesday', 'Wednesday': 'Wednesday',
            'Thursday': 'Thursday', 'Friday': 'Friday', 'Saturday': 'Saturday', 'Sunday': 'Sunday',
        },
    },
    'Spanish': {
        'every': 'Cada',
        'at': 'a las',
        'days': {
            'Monday': 'lunes', 'Tuesday': 'martes', 'Wednesday': 'miercoles',
            'Thursday': 'jueves', 'Friday': 'viernes', 'Saturday': 'sabado', 'Sunday': 'domingo',
        },
    },
    'Italian': {
        'every': 'Ogni',
        'at': 'alle',
        'days': {
            'Monday': 'lunedi', 'Tuesday': 'martedi', 'Wednesday': 'mercoledi',
            'Thursday': 'giovedi', 'Friday': 'venerdi', 'Saturday': 'sabato', 'Sunday': 'domenica',
        },
    },
    'Portuguese': {
        'every': 'Toda',
        'at': 'as',
        'days': {
            'Monday': 'segunda-feira', 'Tuesday': 'terca-feira', 'Wednesday': 'quarta-feira',
            'Thursday': 'quinta-feira', 'Friday': 'sexta-feira', 'Saturday': 'sabado', 'Sunday': 'domingo',
        },
    },
    'German': {
        'every': 'Jeden',
        'at': 'um',
        'days': {
            'Monday': 'Montag', 'Tuesday': 'Dienstag', 'Wednesday': 'Mittwoch',
            'Thursday': 'Donnerstag', 'Friday': 'Freitag', 'Saturday': 'Samstag', 'Sunday': 'Sonntag',
        },
    },
}


# ── DB helpers ────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file, subfolder):
    if not (file and file.filename and allowed_file(file.filename)):
        return None
    ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
    filename = ts + '_' + secure_filename(file.filename)
    if subfolder == 'images':
        dest = os.path.join(BASE_DIR, 'static', 'images')
        stored_path = f'images/{filename}'
    else:
        dest = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
        stored_path = f'uploads/{subfolder}/{filename}'
    os.makedirs(dest, exist_ok=True)
    file.save(os.path.join(dest, filename))
    return stored_path


# ── CSRF protection ───────────────────────────────────────────────────────────
def get_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def schedule_label(day_of_week, start_time, language):
    terms = SCHEDULE_TERMS.get(language) or SCHEDULE_TERMS['English']
    day_txt = terms['days'].get(day_of_week, day_of_week)
    return f"{terms['every']} {day_txt} {terms['at']} {start_time}"


def image_path(filename):
    if not filename or filename == 'placeholder':
        return filename
    cleaned = filename.replace('\\', '/')
    if cleaned.startswith('images/'):
        return cleaned
    for prefix in ('uploads/tour_photos/', 'uploads/tours/', 'tour_photos/', 'tours/'):
        if cleaned.startswith(prefix):
            return 'images/' + cleaned[len(prefix):]
    return 'images/' + cleaned.split('/')[-1]


@app.before_request
def csrf_protect():
    if request.method == 'POST':
        token = session.get('_csrf_token')
        form_token = request.form.get('_csrf_token')
        if not token or token != form_token:
            abort(403)


@app.context_processor
def inject_globals():
    return {
        'csrf_token': get_csrf_token(),
        'current_year': datetime.now().year,
        'schedule_label': schedule_label,
        'image_path': image_path,
    }


# ── User model ────────────────────────────────────────────────────────────────
class User(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.first_name = row['first_name']
        self.last_name = row['last_name']
        self.email = row['email']
        self.role = row['role']

    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    def is_guide(self):
        return self.role == 'guide'

    def is_participant(self):
        return self.role == 'participant'

    def is_admin(self):
        return self.role == 'admin'


@login_manager.user_loader
def load_user(uid):
    db = get_db()
    row = db.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()
    db.close()
    return User(row) if row else None


# ── Schema creation ───────────────────────────────────────────────────────────
def create_tables():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name    TEXT NOT NULL,
            last_name     TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL CHECK(role IN ('guide','participant','admin'))
        );
        CREATE TABLE IF NOT EXISTS guide_languages (
            guide_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            language TEXT NOT NULL,
            PRIMARY KEY (guide_id, language)
        );
        CREATE TABLE IF NOT EXISTS tours (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            title            TEXT NOT NULL,
            guide_id         INTEGER NOT NULL REFERENCES users(id),
            meeting_point    TEXT NOT NULL,
            duration         INTEGER NOT NULL,
            language         TEXT NOT NULL,
            theme            TEXT NOT NULL DEFAULT 'Historical',
            max_participants INTEGER NOT NULL,
            description      TEXT NOT NULL,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tour_stops (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            tour_id   INTEGER NOT NULL REFERENCES tours(id) ON DELETE CASCADE,
            stop_name TEXT NOT NULL,
            order_num INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS tour_schedule (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tour_id     INTEGER NOT NULL REFERENCES tours(id) ON DELETE CASCADE,
            day_of_week TEXT NOT NULL,
            start_time  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tour_photos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            tour_id   INTEGER NOT NULL REFERENCES tours(id) ON DELETE CASCADE,
            filename  TEXT NOT NULL,
            order_num INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS reservations (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER NOT NULL REFERENCES users(id),
            tour_id        INTEGER NOT NULL REFERENCES tours(id),
            tour_date      TEXT NOT NULL,
            start_time     TEXT NOT NULL,
            num_people     INTEGER NOT NULL DEFAULT 1,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS reservation_guests (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL REFERENCES reservations(id) ON DELETE CASCADE,
            first_name     TEXT NOT NULL,
            last_name      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tour_reports (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            tour_id             INTEGER NOT NULL REFERENCES tours(id),
            tour_date           TEXT NOT NULL,
            actual_participants INTEGER NOT NULL,
            photo_filename      TEXT,
            reported_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tour_id, tour_date)
        );
    ''')
    tour_cols = [r['name'] for r in db.execute('PRAGMA table_info(tours)').fetchall()]
    if 'theme' not in tour_cols:
        db.execute("ALTER TABLE tours ADD COLUMN theme TEXT NOT NULL DEFAULT 'Historical'")
    db.commit()
    db.close()


# ── Business logic helpers ────────────────────────────────────────────────────
_SCHED_ORDER = (
    "CASE day_of_week "
    "WHEN 'Monday' THEN 0 WHEN 'Tuesday' THEN 1 WHEN 'Wednesday' THEN 2 "
    "WHEN 'Thursday' THEN 3 WHEN 'Friday' THEN 4 WHEN 'Saturday' THEN 5 WHEN 'Sunday' THEN 6 END"
)


def get_upcoming_dates(tour_id, weeks=6):
    db = get_db()
    schedule = db.execute(
        f'SELECT day_of_week, start_time FROM tour_schedule WHERE tour_id = ? ORDER BY {_SCHED_ORDER}',
        (tour_id,)
    ).fetchall()
    db.close()
    today = date.today()
    results = []
    for s in schedule:
        target_wd = DAY_NUM[s['day_of_week']]
        diff = (target_wd - today.weekday()) % 7 or 7
        start_d = today + timedelta(days=diff)
        for w in range(weeks):
            d = start_d + timedelta(weeks=w)
            results.append({
                'date': d.strftime('%Y-%m-%d'),
                'day': s['day_of_week'],
                'start_time': s['start_time'],
                'display': d.strftime('%A, %d %B %Y') + ' at ' + s['start_time'],
            })
    results.sort(key=lambda x: x['date'])
    return results


def available_spots(tour_id, tour_date, max_participants):
    db = get_db()
    taken = db.execute(
        'SELECT COALESCE(SUM(num_people), 0) AS t FROM reservations WHERE tour_id = ? AND tour_date = ?',
        (tour_id, tour_date)
    ).fetchone()['t']
    db.close()
    return max_participants - taken


def check_overlap(participant_id, tour_date, start_time_str, duration_min, exclude_id=None):
    db = get_db()
    q = ('SELECT r.id, r.start_time, t.duration FROM reservations r '
         'JOIN tours t ON r.tour_id = t.id '
         'WHERE r.participant_id = ? AND r.tour_date = ?')
    args = [participant_id, tour_date]
    if exclude_id:
        q += ' AND r.id != ?'
        args.append(exclude_id)
    rows = db.execute(q, args).fetchall()
    db.close()
    new_s = datetime.strptime(f'{tour_date} {start_time_str}', '%Y-%m-%d %H:%M')
    new_e = new_s + timedelta(minutes=duration_min)
    for row in rows:
        ex_s = datetime.strptime(f'{tour_date} {row["start_time"]}', '%Y-%m-%d %H:%M')
        ex_e = ex_s + timedelta(minutes=row['duration'])
        if new_s < ex_e and new_e > ex_s:
            return True
    return False


def has_reservations(tour_id):
    db = get_db()
    r = db.execute('SELECT 1 FROM reservations WHERE tour_id = ? LIMIT 1', (tour_id,)).fetchone()
    db.close()
    return r is not None


def collect_guest_names(form):
    guests = []
    for i in range(1, 4):
        gfn = form.get(f'guest_fn_{i}', '').strip()
        gln = form.get(f'guest_ln_{i}', '').strip()
        if gfn and gln:
            guests.append((gfn, gln))
    return guests


def validate_basic_reservation_input(tour_date, num_str, guests):
    errors = []
    if not tour_date:
        errors.append('Please select a tour date.')
    if not num_str.isdigit() or not (1 <= int(num_str) <= 4):
        errors.append('Number of people must be between 1 and 4.')

    num_people = int(num_str) if num_str.isdigit() else 1
    if not errors and len(guests) != max(0, num_people - 1):
        errors.append('Please provide first and last names for all additional participants.')

    return num_people, errors


def validate_reservation_rules(db, tour_id, participant_id, tour, tour_date, start_time, num_people):
    errors = []
    try:
        td_obj = datetime.strptime(tour_date, '%Y-%m-%d').date()
        day_name = td_obj.strftime('%A')
        if td_obj <= date.today():
            errors.append('You cannot reserve a past or current-day tour.')

        valid_sched = db.execute(
            'SELECT start_time FROM tour_schedule WHERE tour_id=? AND day_of_week=? AND start_time=?',
            (tour_id, day_name, start_time)
        ).fetchone()
        if not valid_sched:
            errors.append('Invalid tour date or time selection.')

        existing = db.execute(
            'SELECT 1 FROM reservations WHERE participant_id=? AND tour_id=? AND tour_date=?',
            (participant_id, tour_id, tour_date)
        ).fetchone()
        if existing:
            errors.append('You already have a reservation for this tour on that date.')

        if not errors:
            spots = available_spots(tour_id, tour_date, tour['max_participants'])
            if num_people > spots:
                errors.append(f'Only {spots} spot(s) available for this date.')
            if check_overlap(participant_id, tour_date, start_time, tour['duration']):
                errors.append('This tour overlaps with another reservation you have.')
    except ValueError:
        errors.append('Invalid date format.')

    return errors


def build_participant_res_data(db, reservations):
    res_data = []
    today = date.today()
    now = datetime.now()
    for res in reservations:
        guests = db.execute(
            'SELECT first_name, last_name FROM reservation_guests WHERE reservation_id = ?',
            (res['id'],)
        ).fetchall()
        td = datetime.strptime(res['tour_date'], '%Y-%m-%d').date()
        tour_dt = datetime.strptime(f"{res['tour_date']} {res['start_time']}", '%Y-%m-%d %H:%M')
        can_cancel = now < tour_dt - timedelta(hours=24) and td >= today
        res_data.append({
            'res': res,
            'guests': guests,
            'can_cancel': can_cancel,
            'is_past': td < today,
        })
    return res_data


def is_safe_url(target):
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ('http', 'https') and ref.netloc == test.netloc


# ── Template filter ───────────────────────────────────────────────────────────
@app.template_filter('duration_fmt')
def duration_fmt(minutes):
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f'{h}h {m}min'
    if h:
        return f'{h}h'
    return f'{m}min'


# ── Public routes ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    db = get_db()
    fd = request.args.get('date', '').strip()
    fdur = request.args.get('duration', '').strip()
    flang = request.args.get('language', '').strip()
    ftheme = request.args.get('theme', '').strip()

    q = ('SELECT t.*, u.first_name || " " || u.last_name AS guide_name '
         'FROM tours t JOIN users u ON t.guide_id = u.id WHERE 1=1')
    params = []
    if flang:
        q += ' AND t.language = ?'
        params.append(flang)
    if ftheme:
        q += ' AND t.theme = ?'
        params.append(ftheme)
    if fdur == 'short':
        q += ' AND t.duration < 60'
    elif fdur == 'medium':
        q += ' AND t.duration BETWEEN 60 AND 120'
    elif fdur == 'long':
        q += ' AND t.duration > 120'

    tours = db.execute(q, params).fetchall()

    if fd:
        try:
            day_name = datetime.strptime(fd, '%Y-%m-%d').strftime('%A')
            tours = [t for t in tours if db.execute(
                'SELECT 1 FROM tour_schedule WHERE tour_id = ? AND day_of_week = ?',
                (t['id'], day_name)
            ).fetchone()]
        except ValueError:
            fd = ''

    result = []
    for t in tours:
        photo = db.execute(
            'SELECT filename FROM tour_photos WHERE tour_id = ? ORDER BY order_num LIMIT 1',
            (t['id'],)
        ).fetchone()
        sched = db.execute(
            f'SELECT day_of_week, start_time FROM tour_schedule WHERE tour_id = ? ORDER BY {_SCHED_ORDER}',
            (t['id'],)
        ).fetchall()
        result.append({'tour': t, 'photo': photo['filename'] if photo else None, 'schedule': sched})

    db.close()
    return render_template('index.html', tours=result, languages=LANGUAGES,
                           themes=THEMES, filter_date=fd, filter_duration=fdur,
                           filter_language=flang, filter_theme=ftheme,
                           today=date.today().strftime('%Y-%m-%d'))


@app.route('/tour/<int:tour_id>')
def tour_detail(tour_id):
    db = get_db()
    tour = db.execute(
        'SELECT t.*, u.first_name || " " || u.last_name AS guide_name, u.id AS gid '
        'FROM tours t JOIN users u ON t.guide_id = u.id WHERE t.id = ?', (tour_id,)
    ).fetchone()
    if not tour:
        db.close()
        abort(404)
    photos = db.execute('SELECT filename FROM tour_photos WHERE tour_id = ? ORDER BY order_num', (tour_id,)).fetchall()
    stops = db.execute('SELECT stop_name FROM tour_stops WHERE tour_id = ? ORDER BY order_num', (tour_id,)).fetchall()
    schedule = db.execute(
        f'SELECT day_of_week, start_time FROM tour_schedule WHERE tour_id = ? ORDER BY {_SCHED_ORDER}',
        (tour_id,)
    ).fetchall()
    db.close()

    upcoming = get_upcoming_dates(tour_id)
    for u in upcoming:
        u['spots'] = available_spots(tour_id, u['date'], tour['max_participants'])

    return render_template('tour_detail.html', tour=tour, photos=photos, stops=stops,
                           schedule=schedule, upcoming=upcoming)


# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route('/register')
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/register/guide', methods=['GET', 'POST'])
def register_guide():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        fn = request.form.get('first_name', '').strip()
        ln = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        pw = request.form.get('password', '')
        pw2 = request.form.get('password2', '')
        langs = request.form.getlist('languages')

        errors = []
        if not fn:
            errors.append('First name is required.')
        if not ln:
            errors.append('Last name is required.')
        if not email or '@' not in email:
            errors.append('A valid email is required.')
        if len(pw) < 8:
            errors.append('Password must be at least 8 characters.')
        if pw != pw2:
            errors.append('Passwords do not match.')
        if not langs:
            errors.append('Select at least one language.')
        if not all(l in LANGUAGES for l in langs):
            errors.append('Invalid language selection.')

        if not errors:
            db = get_db()
            try:
                if db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
                    errors.append('Email already registered.')
                else:
                    cur = db.execute(
                        'INSERT INTO users (first_name, last_name, email, password_hash, role) VALUES (?,?,?,?,?)',
                        (fn, ln, email, generate_password_hash(pw, method='pbkdf2:sha256'), 'guide')
                    )
                    uid = cur.lastrowid
                    for lang in langs:
                        db.execute('INSERT INTO guide_languages (guide_id, language) VALUES (?,?)', (uid, lang))
                    db.commit()
                    flash('Registration successful! Please log in.', 'success')
                    return redirect(url_for('login'))
            except Exception:
                db.rollback()
                errors.append('An error occurred. Please try again.')
            finally:
                db.close()

        for e in errors:
            flash(e, 'danger')

    return render_template('register_guide.html', languages=LANGUAGES)


@app.route('/register/participant', methods=['GET', 'POST'])
def register_participant():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        fn = request.form.get('first_name', '').strip()
        ln = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        pw = request.form.get('password', '')
        pw2 = request.form.get('password2', '')

        errors = []
        if not fn:
            errors.append('First name is required.')
        if not ln:
            errors.append('Last name is required.')
        if not email or '@' not in email:
            errors.append('A valid email is required.')
        if len(pw) < 8:
            errors.append('Password must be at least 8 characters.')
        if pw != pw2:
            errors.append('Passwords do not match.')

        if not errors:
            db = get_db()
            try:
                if db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
                    errors.append('Email already registered.')
                else:
                    db.execute(
                        'INSERT INTO users (first_name, last_name, email, password_hash, role) VALUES (?,?,?,?,?)',
                        (fn, ln, email, generate_password_hash(pw, method='pbkdf2:sha256'), 'participant')
                    )
                    db.commit()
                    flash('Registration successful! Please log in.', 'success')
                    return redirect(url_for('login'))
            except Exception:
                db.rollback()
                errors.append('An error occurred. Please try again.')
            finally:
                db.close()

        for e in errors:
            flash(e, 'danger')

    return render_template('register_participant.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw = request.form.get('password', '')
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        db.close()
        if row and check_password_hash(row['password_hash'], pw):
            login_user(User(row))
            next_page = request.args.get('next')
            if next_page and is_safe_url(next_page):
                return redirect(next_page)
            return redirect(url_for('index'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ── Guide routes ──────────────────────────────────────────────────────────────
@app.route('/guide/profile')
@login_required
def guide_profile():
    if not current_user.is_guide():
        abort(403)
    db = get_db()
    tours = db.execute(
        'SELECT * FROM tours WHERE guide_id = ? ORDER BY created_at DESC', (current_user.id,)
    ).fetchall()
    langs = [r['language'] for r in db.execute(
        'SELECT language FROM guide_languages WHERE guide_id = ?', (current_user.id,)
    ).fetchall()]

    tours_data = []
    today_str = date.today().strftime('%Y-%m-%d')
    for t in tours:
        photo = db.execute(
            'SELECT filename FROM tour_photos WHERE tour_id = ? ORDER BY order_num LIMIT 1', (t['id'],)
        ).fetchone()
        sched = db.execute(
            f'SELECT day_of_week, start_time FROM tour_schedule WHERE tour_id = ? ORDER BY {_SCHED_ORDER}',
            (t['id'],)
        ).fetchall()
        res_dates = db.execute(
            'SELECT tour_date, start_time, SUM(num_people) AS total_people, COUNT(*) AS num_res '
            'FROM reservations WHERE tour_id = ? GROUP BY tour_date ORDER BY tour_date',
            (t['id'],)
        ).fetchall()
        reportable = []
        for rd in res_dates:
            if rd['tour_date'] < today_str:
                if not db.execute(
                    'SELECT 1 FROM tour_reports WHERE tour_id = ? AND tour_date = ?',
                    (t['id'], rd['tour_date'])
                ).fetchone():
                    reportable.append(rd['tour_date'])
        tours_data.append({
            'tour': t,
            'photo': photo['filename'] if photo else None,
            'schedule': sched,
            'res_dates': res_dates,
            'reportable': reportable,
            'locked': len(res_dates) > 0,
        })
    db.close()
    return render_template('guide_profile.html', tours_data=tours_data, langs=langs,
                           today=date.today().strftime('%Y-%m-%d'))


@app.route('/create_tour', methods=['GET', 'POST'])
@login_required
def create_tour():
    if not current_user.is_guide():
        abort(403)
    db = get_db()
    guide_langs = [r['language'] for r in db.execute(
        'SELECT language FROM guide_languages WHERE guide_id = ?', (current_user.id,)
    ).fetchall()]
    db.close()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        meeting_point = request.form.get('meeting_point', '').strip()
        duration = request.form.get('duration', '').strip()
        language = request.form.get('language', '').strip()
        theme = request.form.get('theme', '').strip()
        max_p = request.form.get('max_participants', '').strip()
        description = request.form.get('description', '').strip()
        schedule_days = request.form.getlist('schedule_days')
        schedule_times = {d: request.form.get(f'time_{d}', '').strip()
                         for d in schedule_days if request.form.get(f'time_{d}', '').strip()}
        stops = [s.strip() for s in request.form.getlist('stop') if s.strip()]
        photos = [p for p in request.files.getlist('photos') if p and p.filename]

        errors = []
        if not title:
            errors.append('Title is required.')
        if not meeting_point:
            errors.append('Meeting point is required.')
        if not duration or not duration.isdigit() or int(duration) <= 0:
            errors.append('Duration must be a positive integer (minutes).')
        if language not in guide_langs:
            errors.append('Select a valid language from your spoken languages.')
        if theme not in THEMES:
            errors.append('Select a valid theme.')
        if not max_p or not max_p.isdigit() or int(max_p) <= 0:
            errors.append('Max participants must be a positive number.')
        if not description:
            errors.append('Description is required.')
        if not schedule_times:
            errors.append('At least one scheduled day with a start time is required.')
        for d in schedule_times:
            if d not in DAYS_OF_WEEK:
                errors.append(f'Invalid day: {d}')
        if len(stops) < 4:
            errors.append('At least 4 stops are required.')
        if len(photos) != 5:
            errors.append('Exactly 5 promotional photos are required.')
        elif not all(allowed_file(p.filename) for p in photos):
            errors.append('All promotional photos must be PNG, JPG, JPEG, GIF, or WebP.')

        if not errors:
            db = get_db()
            try:
                cur = db.execute(
                    'INSERT INTO tours (title, guide_id, meeting_point, duration, language, '
                    'theme, max_participants, description) VALUES (?,?,?,?,?,?,?,?)',
                    (title, current_user.id, meeting_point, int(duration),
                     language, theme, int(max_p), description)
                )
                tid = cur.lastrowid
                for i, stop in enumerate(stops):
                    db.execute('INSERT INTO tour_stops (tour_id, stop_name, order_num) VALUES (?,?,?)',
                               (tid, stop, i))
                for day, t in schedule_times.items():
                    db.execute('INSERT INTO tour_schedule (tour_id, day_of_week, start_time) VALUES (?,?,?)',
                               (tid, day, t))
                for i, photo in enumerate(photos[:5]):
                    fn = save_upload(photo, 'images')
                    if fn:
                        db.execute('INSERT INTO tour_photos (tour_id, filename, order_num) VALUES (?,?,?)',
                                   (tid, fn, i))
                db.commit()
                flash('Tour created successfully!', 'success')
                return redirect(url_for('guide_profile'))
            except Exception:
                db.rollback()
                flash('An error occurred while creating the tour.', 'danger')
            finally:
                db.close()
        else:
            for e in errors:
                flash(e, 'danger')

    return render_template('create_tour.html', languages=guide_langs, themes=THEMES,
                           days=DAYS_OF_WEEK)


@app.route('/edit_tour/<int:tour_id>', methods=['GET', 'POST'])
@login_required
def edit_tour(tour_id):
    if not current_user.is_guide():
        abort(403)
    db = get_db()
    tour = db.execute('SELECT * FROM tours WHERE id = ? AND guide_id = ?',
                      (tour_id, current_user.id)).fetchone()
    if not tour:
        db.close()
        abort(404)
    locked = has_reservations(tour_id)
    guide_langs = [r['language'] for r in db.execute(
        'SELECT language FROM guide_languages WHERE guide_id = ?', (current_user.id,)
    ).fetchall()]
    stops = db.execute('SELECT stop_name FROM tour_stops WHERE tour_id = ? ORDER BY order_num', (tour_id,)).fetchall()
    schedule = db.execute('SELECT day_of_week, start_time FROM tour_schedule WHERE tour_id = ?', (tour_id,)).fetchall()
    photos = db.execute('SELECT id, filename FROM tour_photos WHERE tour_id = ? ORDER BY order_num', (tour_id,)).fetchall()
    db.close()
    sched_dict = {s['day_of_week']: s['start_time'] for s in schedule}

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        new_stops = [s.strip() for s in request.form.getlist('stop') if s.strip()]
        new_photos = [p for p in request.files.getlist('new_photos') if p and p.filename]

        errors = []
        if not title:
            errors.append('Title is required.')
        if not description:
            errors.append('Description is required.')
        if len(new_stops) < 4:
            errors.append('At least 4 stops are required.')
        if new_photos and not all(allowed_file(p.filename) for p in new_photos):
            errors.append('New photos must be PNG, JPG, JPEG, GIF, or WebP.')

        meeting_point = language = duration = max_p = None
        theme = None
        schedule_times = {}
        if not locked:
            meeting_point = request.form.get('meeting_point', '').strip()
            duration = request.form.get('duration', '').strip()
            language = request.form.get('language', '').strip()
            theme = request.form.get('theme', '').strip()
            max_p = request.form.get('max_participants', '').strip()
            schedule_days = request.form.getlist('schedule_days')
            schedule_times = {d: request.form.get(f'time_{d}', '').strip()
                             for d in schedule_days if request.form.get(f'time_{d}', '').strip()}
            if not meeting_point:
                errors.append('Meeting point is required.')
            if not duration or not duration.isdigit() or int(duration) <= 0:
                errors.append('Duration must be a positive integer.')
            if language not in guide_langs:
                errors.append('Select a valid language.')
            if theme not in THEMES:
                errors.append('Select a valid theme.')
            if not max_p or not max_p.isdigit() or int(max_p) <= 0:
                errors.append('Max participants must be a positive number.')
            if not schedule_times:
                errors.append('At least one scheduled day with a start time is required.')

        if not errors:
            db = get_db()
            try:
                if locked:
                    db.execute('UPDATE tours SET title=?, description=? WHERE id=?',
                               (title, description, tour_id))
                else:
                    db.execute(
                        'UPDATE tours SET title=?, meeting_point=?, duration=?, language=?, theme=?, '
                        'max_participants=?, description=? WHERE id=?',
                        (title, meeting_point, int(duration), language, theme,
                         int(max_p), description, tour_id)
                    )
                    db.execute('DELETE FROM tour_schedule WHERE tour_id=?', (tour_id,))
                    for day, t in schedule_times.items():
                        db.execute('INSERT INTO tour_schedule (tour_id, day_of_week, start_time) VALUES (?,?,?)',
                                   (tour_id, day, t))
                db.execute('DELETE FROM tour_stops WHERE tour_id=?', (tour_id,))
                for i, stop in enumerate(new_stops):
                    db.execute('INSERT INTO tour_stops (tour_id, stop_name, order_num) VALUES (?,?,?)',
                               (tour_id, stop, i))
                if new_photos:
                    cnt = db.execute('SELECT COUNT(*) AS c FROM tour_photos WHERE tour_id=?', (tour_id,)).fetchone()['c']
                    for i, photo in enumerate(new_photos):
                        fn = save_upload(photo, 'images')
                        if fn:
                            db.execute('INSERT INTO tour_photos (tour_id, filename, order_num) VALUES (?,?,?)',
                                       (tour_id, fn, cnt + i))
                db.commit()
                flash('Tour updated successfully!', 'success')
                return redirect(url_for('guide_profile'))
            except Exception:
                db.rollback()
                flash('An error occurred while updating the tour.', 'danger')
            finally:
                db.close()
        else:
            for e in errors:
                flash(e, 'danger')

    return render_template('edit_tour.html', tour=tour, locked=locked, languages=guide_langs,
                           themes=THEMES,
                           stops=stops, schedule=schedule, photos=photos, days=DAYS_OF_WEEK,
                           sched_dict=sched_dict)


@app.route('/tour/<int:tour_id>/reservations')
@login_required
def tour_reservations(tour_id):
    if not current_user.is_guide():
        abort(403)
    db = get_db()
    tour = db.execute('SELECT * FROM tours WHERE id = ? AND guide_id = ?',
                      (tour_id, current_user.id)).fetchone()
    if not tour:
        db.close()
        abort(404)
    reservations = db.execute(
        'SELECT r.*, u.first_name || " " || u.last_name AS participant_name '
        'FROM reservations r JOIN users u ON r.participant_id = u.id '
        'WHERE r.tour_id = ? ORDER BY r.tour_date, r.start_time', (tour_id,)
    ).fetchall()
    res_data = []
    for res in reservations:
        guests = db.execute(
            'SELECT first_name, last_name FROM reservation_guests WHERE reservation_id = ?',
            (res['id'],)
        ).fetchall()
        report = db.execute(
            'SELECT * FROM tour_reports WHERE tour_id = ? AND tour_date = ?',
            (tour_id, res['tour_date'])
        ).fetchone()
        res_data.append({'res': res, 'guests': guests, 'report': report})
    db.close()
    return render_template('tour_reservations.html', tour=tour, res_data=res_data)


@app.route('/report_tour/<int:tour_id>/<tour_date>', methods=['GET', 'POST'])
@login_required
def report_tour(tour_id, tour_date):
    if not current_user.is_guide():
        abort(403)
    db = get_db()
    tour = db.execute('SELECT * FROM tours WHERE id = ? AND guide_id = ?',
                      (tour_id, current_user.id)).fetchone()
    if not tour:
        db.close()
        abort(404)
    try:
        td = datetime.strptime(tour_date, '%Y-%m-%d').date()
    except ValueError:
        db.close()
        abort(400)
    if td >= date.today():
        db.close()
        flash('You can only report on past tour dates.', 'warning')
        return redirect(url_for('guide_profile'))
    if db.execute('SELECT 1 FROM tour_reports WHERE tour_id=? AND tour_date=?', (tour_id, tour_date)).fetchone():
        db.close()
        flash('Report already submitted for this date.', 'info')
        return redirect(url_for('guide_profile'))
    total_reserved = db.execute(
        'SELECT COALESCE(SUM(num_people),0) AS t FROM reservations WHERE tour_id=? AND tour_date=?',
        (tour_id, tour_date)
    ).fetchone()['t']
    db.close()

    if request.method == 'POST':
        actual = request.form.get('actual_participants', '').strip()
        photo = request.files.get('report_photo')
        errors = []
        if not actual or not actual.isdigit() or int(actual) < 0:
            errors.append('Actual participants must be a non-negative number.')
        if not photo or not photo.filename:
            errors.append('A report photo is required.')
        elif not allowed_file(photo.filename):
            errors.append('Report photo must be PNG, JPG, JPEG, GIF, or WebP.')
        if not errors:
            photo_fn = save_upload(photo, 'reports')
            db = get_db()
            try:
                db.execute(
                    'INSERT INTO tour_reports (tour_id, tour_date, actual_participants, photo_filename) '
                    'VALUES (?,?,?,?)', (tour_id, tour_date, int(actual), photo_fn)
                )
                db.commit()
                flash('Report submitted successfully!', 'success')
                return redirect(url_for('guide_profile'))
            except Exception:
                db.rollback()
                flash('An error occurred.', 'danger')
            finally:
                db.close()
        else:
            for e in errors:
                flash(e, 'danger')

    return render_template('report_tour.html', tour=tour, tour_date=tour_date,
                           total_reserved=total_reserved)


# ── Participant routes ─────────────────────────────────────────────────────────
@app.route('/participant/profile')
@login_required
def participant_profile():
    if not current_user.is_participant():
        abort(403)
    db = get_db()
    reservations = db.execute(
        'SELECT r.*, t.title, t.meeting_point, t.duration, '
        'u.first_name || " " || u.last_name AS guide_name '
        'FROM reservations r JOIN tours t ON r.tour_id = t.id '
        'JOIN users u ON t.guide_id = u.id '
        'WHERE r.participant_id = ? ORDER BY r.tour_date, r.start_time',
        (current_user.id,)
    ).fetchall()
    res_data = build_participant_res_data(db, reservations)
    db.close()
    return render_template('participant_profile.html', res_data=res_data)


@app.route('/reserve/<int:tour_id>', methods=['POST'])
@login_required
def reserve(tour_id):
    if not current_user.is_participant():
        flash('Only participants can make reservations.', 'danger')
        return redirect(url_for('tour_detail', tour_id=tour_id))

    db = get_db()
    tour = db.execute('SELECT * FROM tours WHERE id = ?', (tour_id,)).fetchone()
    if not tour:
        db.close()
        abort(404)

    tour_date = request.form.get('tour_date', '').strip()
    start_time = request.form.get('start_time', '').strip()
    num_str = request.form.get('num_people', '1').strip()
    guests = collect_guest_names(request.form)

    num_people, errors = validate_basic_reservation_input(tour_date, num_str, guests)

    if not errors:
        errors.extend(
            validate_reservation_rules(
                db,
                tour_id,
                current_user.id,
                tour,
                tour_date,
                start_time,
                num_people,
            )
        )

    if not errors:
        try:
            expected_guests = num_people - 1
            cur = db.execute(
                'INSERT INTO reservations (participant_id, tour_id, tour_date, start_time, num_people) '
                'VALUES (?,?,?,?,?)', (current_user.id, tour_id, tour_date, start_time, num_people)
            )
            rid = cur.lastrowid
            for gfn, gln in guests[:expected_guests]:
                db.execute('INSERT INTO reservation_guests (reservation_id, first_name, last_name) VALUES (?,?,?)',
                           (rid, gfn, gln))
            db.commit()
            flash('Reservation confirmed! See you on the tour.', 'success')
            db.close()
            return redirect(url_for('participant_profile'))
        except Exception:
            db.rollback()
            flash('An error occurred while making the reservation.', 'danger')

    db.close()
    for e in errors:
        flash(e, 'danger')
    return redirect(url_for('tour_detail', tour_id=tour_id))


@app.route('/cancel_reservation/<int:res_id>', methods=['POST'])
@login_required
def cancel_reservation(res_id):
    if not current_user.is_participant():
        abort(403)
    db = get_db()
    res = db.execute(
        'SELECT r.*, t.duration FROM reservations r JOIN tours t ON r.tour_id = t.id '
        'WHERE r.id = ? AND r.participant_id = ?', (res_id, current_user.id)
    ).fetchone()
    if not res:
        db.close()
        abort(404)
    tour_dt = datetime.strptime(f"{res['tour_date']} {res['start_time']}", '%Y-%m-%d %H:%M')
    if datetime.now() >= tour_dt - timedelta(hours=24):
        db.close()
        flash('Cannot cancel within 24 hours of the tour start time.', 'danger')
        return redirect(url_for('participant_profile'))
    try:
        db.execute('DELETE FROM reservations WHERE id = ?', (res_id,))
        db.commit()
        flash('Reservation cancelled successfully.', 'success')
    except Exception:
        db.rollback()
        flash('An error occurred.', 'danger')
    finally:
        db.close()
    return redirect(url_for('participant_profile'))


# ── Admin routes ──────────────────────────────────────────────────────────────
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin():
        abort(403)
    db = get_db()
    stats = {
        'guides': db.execute("SELECT COUNT(*) AS c FROM users WHERE role='guide'").fetchone()['c'],
        'participants': db.execute("SELECT COUNT(*) AS c FROM users WHERE role='participant'").fetchone()['c'],
        'tours': db.execute('SELECT COUNT(*) AS c FROM tours').fetchone()['c'],
        'reservations': db.execute('SELECT COUNT(*) AS c FROM reservations').fetchone()['c'],
        'res_by_lang': db.execute(
            'SELECT t.language, COUNT(r.id) AS cnt FROM reservations r '
            'JOIN tours t ON r.tour_id = t.id GROUP BY t.language ORDER BY cnt DESC'
        ).fetchall(),
    }
    admins = db.execute(
        "SELECT id, first_name, last_name, email FROM users WHERE role = 'admin' ORDER BY id DESC"
    ).fetchall()
    participants = db.execute(
        "SELECT id, first_name, last_name, email FROM users WHERE role = 'participant' ORDER BY id DESC"
    ).fetchall()
    guides = db.execute(
        "SELECT u.*, GROUP_CONCAT(gl.language, ', ') AS languages "
        'FROM users u LEFT JOIN guide_languages gl ON u.id = gl.guide_id '
        "WHERE u.role = 'guide' GROUP BY u.id"
    ).fetchall()
    guides_data = []
    for g in guides:
        tours = db.execute('SELECT * FROM tours WHERE guide_id = ?', (g['id'],)).fetchall()
        t_data = []
        for t in tours:
            sched = db.execute(
                f'SELECT day_of_week, start_time FROM tour_schedule WHERE tour_id=? ORDER BY {_SCHED_ORDER}',
                (t['id'],)
            ).fetchall()
            stops = db.execute('SELECT stop_name FROM tour_stops WHERE tour_id=? ORDER BY order_num', (t['id'],)).fetchall()
            res_count = db.execute('SELECT COUNT(*) AS c FROM reservations WHERE tour_id=?', (t['id'],)).fetchone()['c']
            t_data.append({'tour': t, 'schedule': sched, 'stops': stops, 'res_count': res_count})
        guides_data.append({'guide': g, 'tours': t_data})
    db.close()
    return render_template(
        'admin.html',
        stats=stats,
        admins=admins,
        participants=participants,
        guides_data=guides_data,
    )


# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', code=403, message='Access Forbidden'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Page Not Found'), 404


@app.errorhandler(413)
def too_large(e):
    return render_template('error.html', code=413, message='File Too Large (max 16 MB)'), 413


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs(os.path.join('static', 'images'), exist_ok=True)
    os.makedirs(os.path.join('static', 'uploads', 'reports'), exist_ok=True)
    create_tables()
    app.run(debug=True)
