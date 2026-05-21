import os
import json

if os.environ.get('GOOGLE_CREDS_JSON'):
    with open('service_account.json', 'w') as f:
        json.dump(json.loads(os.environ.get('GOOGLE_CREDS_JSON')), f)
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