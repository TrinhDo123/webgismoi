import os
print(os.name)
import sys
import json
import ee
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import pandas as pd
from sklearn.linear_model import LinearRegression
import io
import numpy as np
from google import genai

# Đọc API Key từ biến môi trường của hệ thống
client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY")
)

app = Flask(__name__)

# ========================================================
# 1. ĐỊNH NGHĨA HÀM KHỞI TẠO DATABASE TRƯỚC (QUAN TRỌNG)
# ========================================================
def init_db():
    conn = sqlite3.connect('data/coastal.db')
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
    conn.close()

# ========================================================
# 2. CHẠY LỆNH KHỞI TẠO THƯ MỤC VÀ DB SAU
# ========================================================
if not os.path.exists('data'):
    os.makedirs('data')

# Gọi hàm sau khi đã định nghĩa ở trên -> Không bao giờ bị NameError
init_db()

CORS(app, resources={
    r"/*": {
        "origins": "*"
    }
})

# ĐỊNH NGHĨA ROUTE TRANG CHỦ (Hiển thị file index.html)
@app.route('/')
def home():
    return render_template('index.html')

# =========================
# SAVE DATA
# =========================
def save_data(province, year, ndwi, mndwi, erosion, accretion):
    conn = sqlite3.connect('data/coastal.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO coastal_analysis(province, year, ndwi, mndwi, erosion, accretion)
    VALUES(?,?,?,?,?,?)
    ''',(province, year, ndwi, mndwi, erosion, accretion))
    conn.commit()
    conn.close()

# =========================
# INIT GEE (Bọc giáp an toàn, dùng đường dẫn tương đối chuẩn)
# =========================
service_account = "gee-coastline@cach-471019.iam.gserviceaccount.com"
cred_path = 'service_account.json'  # <-- Đường dẫn tương đối chuẩn cho Render

env_creds = os.environ.get('GOOGLE_CREDS_JSON')

if env_creds:
    try:
        clean_creds = env_creds.strip()
        cred_data = json.loads(clean_creds)
        with open(cred_path, 'w') as f:
            json.dump(cred_data, f)
        print("Successfully generated service_account.json from Render Environment.")
    except Exception as e:
        print(f"Critical Error parsing GOOGLE_CREDS_JSON env: {str(e)}")
else:
    print("Running in local mode / No GOOGLE_CREDS_JSON env detected. Using local service_account.json file.")

# Sử dụng biến cred_path đồng bộ cho mọi môi trường
try:
    credentials = ee.ServiceAccountCredentials(service_account, cred_path)
    ee.Initialize(credentials)
    print("Google Earth Engine initialized successfully!")
except Exception as e:
    print(f"GEE Initialization failed: {str(e)}")
    credentials = None

# =========================
# DATA
# =========================
coastal_data = [
    {"label":"An Giang", "search":["Kien Giang","An Giang"]},
    {"label":"Bac Ninh", "search":["Bac Giang","Bac Ninh"]},
    {"label":"Ca Mau", "search":["Bac Lieu","Ca Mau"]},
    {"label":"Cao Bang", "search":["Cao Bang"]},
    {"label":"Dak Lak", "search":["Phu Yen","Dak Lak"]},
    {"label":"Dien Bien", "search":["Dien Bien"]},
    {"label":"Dong Nai", "search":["Binh Phuoc","Dong Nai"]},
    {"label":"Dong Thap", "search":["Tien Giang","Dong Thap"]},
    {"label":"Gia Lai", "search":["Gia Lai","Binh Dinh"]},
    {"label":"Ha Tinh", "search":["Ha Tinh"]},
    {"label":"Hung Yen", "search":["Thai Binh","Hung Yen"]},
    {"label":"Khanh Hoa", "search":["Khanh Hoa","Ninh Thuan"]},
    {"label":"Lai Chau", "search":["Lai Chau"]},
    {"label":"Lam Dong", "search":["Dak Nong","Lam Dong","Binh Thuan"]},
    {"label":"Lang Son", "search":["Lang Son"]},
    {"label":"Lao Cai", "search":["Lao Cai","Yen Bai"]},
    {"label":"Nghe An", "search":["Nghe An"]},
    {"label":"Ninh Binh", "search":["Ha Nam","Ninh Binh","Nam Dinh"]},
    {"label":"Phu Tho", "search":["Hoa Binh","Vinh Phuc","Phu Tho"]},
    {"label":"Quang Ngai", "search":["Quang Ngai","Kon Tum"]},
    {"label":"Quang Ninh", "search":["Quang Ninh"]},
    {"label":"Quang Tri", "search":["Quang Binh","Quang Tri"]},
    {"label":"Son La", "search":["Son La"]},
    {"label":"Tay Ninh", "search":["Long An","Tay Ninh"]},
    {"label":"Thai Nguyen", "search":["Bac Kan","Thai Nguyen"]},
    {"label":"Thanh Hoa", "search":["Thanh Hoa"]},
    {"label":"Can Tho", "search":["Soc Trang","Hau Giang","Can Tho"]},
    {"label":"Da Nang", "search":["Quang Nam","Da Nang"]},
    {"label":"Ha Noi", "search":["Ha Noi"]},
    {"label":"Hai Phong", "search":["Hai Duong","Hai Phong"]},
    {"label":"TP Ho Chi Minh", "search":["Binh Duong","Ho Chi Minh","Ba Ria"]},
    {"label":"Hue", "search":["Thua Thien Hue"]},
    {"label":"Tuyen Quang", "search":["Ha Giang","Tuyen Quang"]},
    {"label":"Vinh Long", "search":["Ben Tre","Vinh Long","Tra Vinh"]}
]

# =========================
# NON COASTAL
# =========================
non_coastal = [
    'Cao Bang', 'Dien Bien', 'Lai Chau', 'Lang Son', 'Son La', 
    'Thai Nguyen', 'Tuyen Quang', 'Lao Cai', 'Phu Tho', 'Bac Ninh', 
    'Dong Nai', 'Tay Ninh', 'Ha Noi'
]

# =========================
# VIETNAM PROVINCES
# =========================
provinces_fc = (
    ee.FeatureCollection("FAO/GAUL/2015/level1")
    .filter(ee.Filter.eq('ADM0_NAME', 'Viet Nam'))
)

# =========================
# GLOBAL WATER
# =========================
gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
permanent_water = gsw.select('occurrence').gt(80)

# =========================
# CLOUD MASK
# =========================
def mask_l8_sr(image):
    qa = image.select('QA_PIXEL')
    cloud = qa.bitwiseAnd(1 << 3).eq(0)
    shadow = qa.bitwiseAnd(1 << 4).eq(0)
    mask = cloud.And(shadow)
    optical = (
        image.select(['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7'])
        .multiply(0.0000275)
        .add(-0.2)
    )
    return optical.updateMask(mask).copyProperties(image, image.propertyNames())

# =========================
# GET ANALYSIS
# =========================
def get_analysis(offshore_zone, year):
    dataset = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(offshore_zone)
        .filterDate(f'{year}-01-01', f'{year}-12-31')
        .filter(ee.Filter.lt('CLOUD_COVER', 20))
        .map(mask_l8_sr)
        .limit(30)
    )
    img = dataset.reduce(ee.Reducer.percentile([25])).clip(offshore_zone)
    
    green = img.select('SR_B3_p25')
    nir   = img.select('SR_B5_p25')
    swir  = img.select('SR_B6_p25')

    ndwi = green.subtract(nir).divide(green.add(nir)).rename('NDWI')
    mndwi = green.subtract(swir).divide(green.add(swir)).rename('MNDWI')
    
    water = mndwi.gt(0.12).And(permanent_water)
    water = water.focal_max(1).focal_min(1)
    water = water.updateMask(water.connectedPixelCount(100, True).gte(100))
    edge = ee.Algorithms.CannyEdgeDetector(image=water, threshold=0.1, sigma=1).selfMask()

    stats = (
        ndwi.addBands(mndwi)
        .reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=offshore_zone,
            scale=120,
            bestEffort=True,
            tileScale=4,
            maxPixels=1e10
        )
        .getInfo()
    )
    return {'ndwi': ndwi, 'mndwi': mndwi, 'water': water.rename('water'), 'edge': edge, 'vals': stats}

# =========================
# FAST AREA
# =========================
def calculate_area(mask, band_name, geometry):
    area_image = ee.Image.pixelArea().updateMask(mask).rename(band_name)
    result = area_image.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry,
        scale=120,
        bestEffort=True,
        tileScale=4,
        maxPixels=1e10
    ).getInfo()
    if result and band_name in result:
        return round(result[band_name] / 10000, 2)
    return 0

# =========================
# API ROUTE
# =========================
@app.route('/gee')
def run_analysis():
    try:
        province = request.args.get('province')
        y1 = request.args.get('y1')
        y2 = request.args.get('y2')

        if province in non_coastal:
            return jsonify({"error": f"Tỉnh {province} không giáp biển"}), 400

        selected = next(d for d in coastal_data if d['label'] == province)
        region = provinces_fc.filter(ee.Filter.inList('ADM1_NAME', selected['search']))
        aoi = region.geometry().dissolve()

        coastal_buffer = aoi.buffer(1000)
        offshore_zone = coastal_buffer.difference(aoi, 1).intersection(aoi.bounds(), 1)

        r1 = get_analysis(offshore_zone, y1)
        r2 = get_analysis(offshore_zone, y2)

        erosion = r1['water'].And(r2['water'].Not()).rename('erosion').updateMask(r1['water'].And(r2['water'].Not()))
        accretion = r2['water'].And(r1['water'].Not()).rename('accretion').updateMask(r2['water'].And(r1['water'].Not()))

        save_data(
            province, int(y1),
            r1['vals'].get('NDWI', 0), r1['vals'].get('MNDWI', 0),
            calculate_area(erosion, 'erosion', offshore_zone),
            calculate_area(accretion, 'accretion', offshore_zone)
        )

        result = {
            "layers": {
                "boundary": ee.Image().byte().paint(featureCollection=ee.FeatureCollection([ee.Feature(aoi)]), color=1, width=3).getMapId({'palette': ['yellow']})['tile_fetcher'].url_format,
                "shoreline1": r1['edge'].getMapId({'palette': ['#ff00ff']})['tile_fetcher'].url_format,
                "shoreline2": r2['edge'].getMapId({'palette': ['#00ffff']})['tile_fetcher'].url_format,
                "erosion": erosion.getMapId({'palette': ['red']})['tile_fetcher'].url_format,
                "accretion": accretion.getMapId({'palette': ['lime']})['tile_fetcher'].url_format,
                "ndwi1": r1['ndwi'].getMapId({'min': -1, 'max': 1, 'palette': ['white', 'blue']})['tile_fetcher'].url_format,
                "ndwi2": r2['ndwi'].getMapId({'min': -1, 'max': 1, 'palette': ['white', 'blue']})['tile_fetcher'].url_format,
                "mndwi1": r1['mndwi'].getMapId({'min': -1, 'max': 1, 'palette': ['white', 'green']})['tile_fetcher'].url_format,
                "mndwi2": r2['mndwi'].getMapId({'min': -1, 'max': 1, 'palette': ['white', 'green']})['tile_fetcher'].url_format
            },
            "stats": {
                "year1": {"NDWI": float(r1['vals'].get('NDWI', 0)), "MNDWI": float(r1['vals'].get('MNDWI', 0))},
                "year2": {"NDWI": float(r2['vals'].get('NDWI', 0)), "MNDWI": float(r2['vals'].get('MNDWI', 0))},
                "erosion_ha": float(calculate_area(erosion, 'erosion', offshore_zone)),
                "accretion_ha": float(calculate_area(accretion, 'accretion', offshore_zone))
            },
            "bounds": aoi.bounds().getInfo()['coordinates'][0]
        }
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# FORECAST AI
# =========================
@app.route('/forecast')
def forecast():
    province = request.args.get('province')
    conn = sqlite3.connect('data/coastal.db')
    df = pd.read_sql_query(f"SELECT * FROM coastal_analysis WHERE province='{province}' ORDER BY year", conn)
    conn.close()

    if len(df) < 2:
        return jsonify({"error": "Không đủ dữ liệu"})

    X = np.array(df['year']).reshape(-1,1)
    y = np.array(df['erosion'])
    model = LinearRegression()
    model.fit(X, y)

    last_year = int(df['year'].max())
    result = []
    for i in range(1, 6):
        year = last_year + i
        pred = model.predict([[year]])[0]
        result.append({"year": year, "prediction": round(float(pred), 2)})
    return jsonify(result)

# =========================
# CHAT AI GIS
# =========================
@app.route('/chat_ai', methods=['POST'])
def chat_ai():
    data = request.get_json()
    prompt = f"Tỉnh: {data['province']}\nDữ liệu: {data['stats']}\nCâu hỏi: {data['question']}"
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    answer = getattr(response, "text", None)
    if not answer:
        return jsonify({"error": "AI không phản hồi"}), 500 
    return jsonify({"answer": answer})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
