import sqlite3

conn = sqlite3.connect(
    'data/coastal.db'
)

cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS coastal_analysis(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    province TEXT,

    year INTEGER,

    ndwi REAL,

    mndwi REAL,

    erosion REAL,

    accretion REAL
)
''')

conn.commit()

print("Database created")