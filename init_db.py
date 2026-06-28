"""
Initialise the database and seed sample data for Antalya City Tours.
Runs once:  python init_db.py
"""
import os
import sqlite3
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

DATABASE = 'antalya_tours.db'

# ── helpers ───────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def next_weekday(target_wd, ahead=1):
    """Return the date of the next occurrence of target weekday (0=Mon).
    ahead=1 means 'skip today even if today is that day'."""
    today = date.today()
    diff = (target_wd - today.weekday()) % 7 or 7
    return today + timedelta(days=diff + (ahead - 1) * 7)


def last_weekday(target_wd):
    """Return the date of the most-recent past occurrence of target weekday."""
    today = date.today()
    diff = (today.weekday() - target_wd) % 7 or 7
    return today - timedelta(days=diff)


# ── schema (imported from app) ─────────────────────────────────────────────────

def create_tables():
    from app import create_tables as _ct
    _ct()


# ── seed ──────────────────────────────────────────────────────────────────────

def seed():
    db = get_db()
    # Wipe existing data (preserves schema)
    db.executescript('''
        DELETE FROM tour_reports;
        DELETE FROM reservation_guests;
        DELETE FROM reservations;
        DELETE FROM tour_photos;
        DELETE FROM tour_schedule;
        DELETE FROM tour_stops;
        DELETE FROM tours;
        DELETE FROM guide_languages;
        DELETE FROM users;
    ''')

    # ── Users ────────────────────────────────────────────────────────────────

    def add_user(fn, ln, email, pw, role):
        db.execute(
            'INSERT INTO users (first_name, last_name, email, password_hash, role) VALUES (?,?,?,?,?)',
            (fn, ln, email, generate_password_hash(pw, method='pbkdf2:sha256'), role)
        )
        return db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()['id']

    admin_id  = add_user('Admin', 'Panel', 'admin@antalya.com', 'adminspecial12345', 'admin')
    guide1_id = add_user('Gulnihal', 'Aktan', 'gaktan@antalyatours.com', 'gaktan12345', 'guide')
    guide2_id = add_user('Leo', 'Valdez', 'leovv@antalyatours.com', 'lelele1206', 'guide')
    guide3_id = add_user('Maria', 'Belluci', 'mariabb@antalyatours.com', 'tiramisu123', 'guide')
    p1_id     = add_user('John', 'Smith', 'john@example.com', 'john12345', 'participant')
    p2_id     = add_user('Maria', 'Garcia', 'maria@example.com', 'mariamaria123', 'participant')
    p3_id     = add_user('Hans', 'Mueller', 'hans@example.com', 'hansmue1234', 'participant')

    # Guide languages
    for lang in ['English']:
        db.execute('INSERT INTO guide_languages VALUES (?,?)', (guide1_id, lang))
    for lang in ['Portuguese', 'Spanish']:
        db.execute('INSERT INTO guide_languages VALUES (?,?)', (guide2_id, lang))
    for lang in ['Italian']:
        db.execute('INSERT INTO guide_languages VALUES (?,?)', (guide3_id, lang))

    # ── Tours ────────────────────────────────────────────────────────────────

    def add_tour(title, guide_id, meeting_point, duration, language, theme, max_p, description):
        cur = db.execute(
            'INSERT INTO tours (title, guide_id, meeting_point, duration, language, '
            'theme, max_participants, description) VALUES (?,?,?,?,?,?,?,?)',
            (title, guide_id, meeting_point, duration, language, theme, max_p, description)
        )
        return cur.lastrowid

    def add_stops(tid, stops):
        for i, s in enumerate(stops):
            db.execute('INSERT INTO tour_stops (tour_id, stop_name, order_num) VALUES (?,?,?)', (tid, s, i))

    def add_sched(tid, days_times):
        for day, t in days_times:
            db.execute('INSERT INTO tour_schedule (tour_id, day_of_week, start_time) VALUES (?,?,?)', (tid, day, t))

    def add_photos(tid, filenames):
        for i, filename in enumerate(filenames):
            db.execute('INSERT INTO tour_photos (tour_id, filename, order_num) VALUES (?,?,?)',
                       (tid, 'images/' + filename, i))

    # Tour 1 – Through Hadrian's Gate (Guide Gulnihal, English)
    t1 = add_tour(
        "Through Hadrian's Gate", guide1_id,
        "Hadrian's Gate (Hadrian Kapisi), Kaleici", 120, 'English', 'Historical', 20,
        "Step through a Roman triumphal arch and into two thousand years of history. "
        "This English-language walking tour winds through the cobblestone lanes of Kaleici, "
        "Antalya's walled old town, uncovering the Roman, Byzantine, Seljuk and Ottoman layers "
        "that define its character. Comfortable shoes and curiosity required."
    )
    add_stops(t1, ["Hadrian's Gate", 'Yivli Minaret Mosque', 'Kesik Minaret (Broken Minaret)',
                   'Hidirlik Tower', 'Kaleici Marina'])
    add_sched(t1, [('Monday', '09:00'), ('Wednesday', '09:00'), ('Friday', '09:00')])
    add_photos(t1, ['hadrian_1.jpg', 'hadrian2.jpg', 'hadrian3.jpg', 'hadrian4.jpg', 'hadrian5.jpeg'])

    # Tour 2 – Spanish tour by Leo Valdez
    t2 = add_tour(
        'Donde las Cascadas se Encuentran con el Mar', guide2_id,
        'Muelle de Kaleici Marina (embarcadero de goleta de madera)',
        180, 'Spanish', 'Recreational Activity', 20,
        'Sube a una goleta tradicional de madera y navega hasta la Cascada de Duden Inferior, '
        'la unica cascada de Turquia que cae directamente al mar. '
        'Durante el recorrido descubriras acantilados calizos, cuevas marinas y panoramas costeros inolvidables.'
    )
    add_stops(t2, ['Salida desde Kaleici Marina', 'Cascada de Duden Inferior (Asagi Duden)',
                   'Cuevas Marinas y Acantilados de Piedra Caliza',
                   'Panorama de la Costa de Konyaalti',
                   'Regreso a Kaleici Marina'])
    add_sched(t2, [('Wednesday', '09:00')])
    add_photos(t2, ['waterfall1.jpg', 'waterfall2.jpeg', 'waterfall3.jpeg', 'waterfall4.jpg', 'waterfall5.jpg'])

    # Tour 3 – Italian tour by Maria Belluci
    t3 = add_tour(
        'Un Assaggio di Antalya', guide3_id,
        'Porta di Adriano (Hadrian Kapisi), Kaleici', 150, 'Italian', 'Food Tour', 12,
        "La scena gastronomica di Antalya e il risultato di secoli di scambi mediterranei "
        "e della tradizione culinaria ottomana di corte. "
        "Questo tour serale a piedi visita quattro ristoranti selezionati, "
        "con degustazioni dei piatti che definiscono l'identita culinaria della citta."
    )
    add_stops(t3, ['Ristorante Seraser Fine Dining', 'Yemenli Meyhanesi',
                   'Ristorante 7 Mehmet', 'Ristorante Parlak'])
    add_sched(t3, [('Thursday', '18:00'), ('Sunday', '18:00')])
    add_photos(t3, ['food1.jpg', 'food2.jpg', 'food3.jpg', 'food4.jpg', 'food5.jpg'])

    # ── Reservations ──────────────────────────────────────────────────────────

    def add_res(pid, tid, d, t, n, guests=None):
        cur = db.execute(
            'INSERT INTO reservations (participant_id, tour_id, tour_date, start_time, num_people) '
            'VALUES (?,?,?,?,?)', (pid, tid, d, t, n)
        )
        rid = cur.lastrowid
        for gfn, gln in (guests or []):
            db.execute('INSERT INTO reservation_guests (reservation_id, first_name, last_name) VALUES (?,?,?)',
                       (rid, gfn, gln))
        return rid

    # Future dates
    next_mon  = next_weekday(0).strftime('%Y-%m-%d')  # Monday    → tour 1
    next_wed  = next_weekday(2).strftime('%Y-%m-%d')  # Wednesday → tour 2
    next_thu  = next_weekday(3).strftime('%Y-%m-%d')  # Thursday  → tour 3
    next_sun  = next_weekday(6).strftime('%Y-%m-%d')  # Sunday    → tour 3
    next_fri  = next_weekday(4).strftime('%Y-%m-%d')  # Friday    → tour 1

    # John: Tour 1 (Mon) – 2 people
    add_res(p1_id, t1, next_mon, '09:00', 2, [('Jane', 'Smith')])
    # Maria: Tour 2 (Wed) – 1 person
    add_res(p2_id, t2, next_wed, '09:00', 1)
    # Hans: Tour 3 (Thu) – 3 people
    add_res(p3_id, t3, next_thu, '18:00', 3, [('Anna', 'Mueller'), ('Klaus', 'Mueller')])
    # John: Tour 3 (Sun) – 2 people
    add_res(p1_id, t3, next_sun, '18:00', 2, [('Emily', 'Smith')])

    # Past reservation + report (Tour 2, last Wednesday)
    past_wed = last_weekday(2).strftime('%Y-%m-%d')
    add_res(p1_id, t2, past_wed, '09:00', 2, [('Bob', 'Smith')])
    db.execute(
        'INSERT INTO tour_reports (tour_id, tour_date, actual_participants, photo_filename) VALUES (?,?,?,?)',
        (t2, past_wed, 14, 'placeholder')
    )

    # Past reservation without report – guide Gulnihal can submit it (Tour 1, last Friday)
    past_fri = last_weekday(4).strftime('%Y-%m-%d')
    add_res(p3_id, t1, past_fri, '09:00', 2, [('Lena', 'Mueller')])

    db.commit()
    db.close()

    print('✓ Database seeded successfully!\n')
    print('Credentials')
    print('───────────────────────────────────────────')
    print(f'  Admin:         admin@antalya.com        / adminspecial12345')
    print(f'  Guide 1:       gaktan@antalyatours.com  / gaktan12345')
    print(f'  Guide 2:       leovv@antalyatours.com   / lelele1206')
    print(f'  Guide 3:       mariabb@antalyatours.com / tiramisu123')
    print(f'  Participant 1: john@example.com         / john12345')
    print(f'  Participant 2: maria@example.com        / mariamaria123')
    print(f'  Participant 3: hans@example.com         / hansmue1234')


if __name__ == '__main__':
    os.makedirs(os.path.join('static', 'images'), exist_ok=True)
    os.makedirs(os.path.join('static', 'uploads', 'reports'), exist_ok=True)
    create_tables()
    seed()
