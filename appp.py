import os
import json
import sqlite3
import traceback

import ee
import numpy as np
import pandas as pd

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from sklearn.linear_model import LinearRegression
from google import genai


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "WebGIS API is running",
        "gee_test": "/gee?province=An%20Giang&y1=2016&y2=2024",
        "gee_test_khanhhoa": "/gee?province=Khanh%20Hoa&y1=2016&y2=2024",
        "forecast_test": "/forecast?province=An%20Giang",
        "chat_ai": "/chat_ai"
    })


def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/coastal.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS coastal_analysis(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        province TEXT,
        year INTEGER,
        ndwi REAL,
        mndwi REAL,
        erosion REAL,
        accretion REAL
    )
    """)
    conn.commit()
    conn.close()


def save_data(province, year, ndwi, mndwi, erosion, accretion):
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/coastal.db")
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO coastal_analysis(province, year, ndwi, mndwi, erosion, accretion)
    VALUES(?,?,?,?,?,?)
    """, (
        province,
        int(year),
        float(ndwi or 0),
        float(mndwi or 0),
        float(erosion or 0),
        float(accretion or 0)
    ))
    conn.commit()
    conn.close()


init_db()

gee_ready = False
provinces_fc = None
tile_cache = {}


def init_gee():
    global gee_ready, provinces_fc

    if gee_ready:
        return

    info = None

    if os.environ.get("GOOGLE_CREDS_JSON"):
        try:
            info = json.loads(os.environ["GOOGLE_CREDS_JSON"])
        except json.JSONDecodeError as e:
            raise ValueError(
                "GOOGLE_CREDS_JSON không phải JSON hợp lệ. "
                "Hãy dán nguyên nội dung file JSON service account vào Render Environment."
            ) from e
        with open("service_account.json", "w", encoding="utf-8") as f:
            json.dump(info, f)
    else:
        if not os.path.exists("service_account.json"):
            raise FileNotFoundError(
                "Không tìm thấy GOOGLE_CREDS_JSON trên Render hoặc service_account.json khi chạy local"
            )
        with open("service_account.json", "r", encoding="utf-8") as f:
            info = json.load(f)

    if not info:
        raise ValueError("Không đọc được service account JSON")

    for key in ["client_email", "private_key", "project_id"]:
        if key not in info:
            raise ValueError(f"service_account.json thiếu {key}")

    credentials = ee.ServiceAccountCredentials(info["client_email"], "service_account.json")

    try:
        ee.Initialize(credentials, project=info["project_id"])
    except TypeError:
        ee.Initialize(credentials)

    provinces_fc = (
        ee.FeatureCollection("FAO/GAUL/2015/level1")
        .filter(ee.Filter.eq("ADM0_NAME", "Viet Nam"))
    )
    gee_ready = True


# Tỉnh mới/gộp tỉnh theo file GEE mẫu bạn gửi
coastal_data = [
    {"label": "An Giang", "search": ["Kien Giang", "An Giang"]},
    {"label": "Bac Ninh", "search": ["Bac Giang", "Bac Ninh"]},
    {"label": "Ca Mau", "search": ["Bac Lieu", "Ca Mau"]},
    {"label": "Cao Bang", "search": ["Cao Bang"]},
    {"label": "Dak Lak", "search": ["Phu Yen", "Dak Lak"]},
    {"label": "Dien Bien", "search": ["Dien Bien"]},
    {"label": "Dong Nai", "search": ["Binh Phuoc", "Dong Nai"]},
    {"label": "Dong Thap", "search": ["Tien Giang", "Dong Thap"]},
    {"label": "Gia Lai", "search": ["Gia Lai", "Binh Dinh"]},
    {"label": "Ha Tinh", "search": ["Ha Tinh"]},
    {"label": "Hung Yen", "search": ["Thai Binh", "Hung Yen"]},
    {"label": "Khanh Hoa", "search": ["Khanh Hoa", "Ninh Thuan"]},
    {"label": "Lai Chau", "search": ["Lai Chau"]},
    {"label": "Lam Dong", "search": ["Dak Nong", "Lam Dong", "Binh Thuan"]},
    {"label": "Lang Son", "search": ["Lang Son"]},
    {"label": "Lao Cai", "search": ["Lao Cai", "Yen Bai"]},
    {"label": "Nghe An", "search": ["Nghe An"]},
    {"label": "Ninh Binh", "search": ["Ha Nam", "Ninh Binh", "Nam Dinh"]},
    {"label": "Phu Tho", "search": ["Hoa Binh", "Vinh Phuc", "Phu Tho"]},
    {"label": "Quang Ngai", "search": ["Quang Ngai", "Kon Tum"]},
    {"label": "Quang Ninh", "search": ["Quang Ninh"]},
    {"label": "Quang Tri", "search": ["Quang Binh", "Quang Tri"]},
    {"label": "Son La", "search": ["Son La"]},
    {"label": "Tay Ninh", "search": ["Long An", "Tay Ninh"]},
    {"label": "Thai Nguyen", "search": ["Bac Kan", "Thai Nguyen"]},
    {"label": "Thanh Hoa", "search": ["Thanh Hoa"]},
    {"label": "Can Tho", "search": ["Soc Trang", "Hau Giang", "Can Tho"]},
    {"label": "Da Nang", "search": ["Quang Nam", "Da Nang"]},
    {"label": "Ha Noi", "search": ["Ha Noi"]},
    {"label": "Hai Phong", "search": ["Hai Duong", "Hai Phong"]},
    {"label": "TP Ho Chi Minh", "search": ["Binh Duong", "Ho Chi Minh", "Ba Ria"]},
    {"label": "Hue", "search": ["Thua Thien Hue"]},
    {"label": "Tuyen Quang", "search": ["Ha Giang", "Tuyen Quang"]},
    {"label": "Vinh Long", "search": ["Ben Tre", "Vinh Long", "Tra Vinh"]}
]

non_coastal = [
    "Cao Bang", "Dien Bien", "Lai Chau", "Lang Son", "Son La", "Thai Nguyen",
    "Tuyen Quang", "Lao Cai", "Phu Tho", "Bac Ninh", "Dong Nai", "Tay Ninh", "Ha Noi"
]


def get_selected(province):
    if province in non_coastal:
        raise ValueError(f"Tỉnh {province} không giáp biển")

    selected = next((d for d in coastal_data if d["label"] == province), None)
    if not selected:
        raise LookupError(f"Không tìm thấy tỉnh {province}")
    return selected


def get_region_and_zone(province):
    """
    Giống logic GEE mẫu:
    - aoi = toàn bộ tỉnh/vùng gộp
    - offshore_zone = dải ngoài ranh giới đất liền để lấy coastline/NDWI/MNDWI
    """
    selected = get_selected(province)
    region = provinces_fc.filter(ee.Filter.inList("ADM1_NAME", selected["search"]))

    count_region = region.size().getInfo()
    if count_region == 0:
        raise LookupError(f"Không tìm thấy ranh giới GEE cho {province}")

    aoi = region.geometry().dissolve()
    coastal_buffer = aoi.buffer(2000)
    offshore_zone = coastal_buffer.difference(aoi, 1).intersection(aoi.bounds(), 1)
    return aoi, offshore_zone


def safe_bounds(geom):
    try:
        return geom.bounds().getInfo()["coordinates"][0]
    except Exception as e:
        print("BOUNDS ERROR:", e)
        return [[104.0, 8.0], [109.5, 8.0], [109.5, 23.0], [104.0, 23.0], [104.0, 8.0]]


def get_map_url(image, vis_params):
    return image.getMapId(vis_params)["tile_fetcher"].url_format


def get_float(dictionary, key):
    if not dictionary:
        return 0.0
    value = dictionary.get(key, 0)
    return 0.0 if value is None else float(value)


def get_analysis(offshore_zone, year):
    """
    Phiên bản GEE-style:
    - Landsat TOA B3/B5/B6 giống code mẫu
    - water = MNDWI threshold
    - smooth water bằng focal_max/focal_min/focal_mode
    - coastline = CannyEdgeDetector sigma=2, liền nét hơn
    """
    l8 = ee.ImageCollection("LANDSAT/LC08/C02/T1_TOA")
    l9 = ee.ImageCollection("LANDSAT/LC09/C02/T1_TOA")

    dataset = (
        l8.merge(l9)
        .filterBounds(offshore_zone)
        .filterDate(f"{year}-01-01", f"{year}-12-31")
        .filter(ee.Filter.lt("CLOUD_COVER", 30))
        .sort("CLOUD_COVER")
        .limit(20)
    )

    img = dataset.median().clip(offshore_zone)

    ndwi = img.normalizedDifference(["B3", "B5"]).rename("NDWI")
    mndwi = img.normalizedDifference(["B3", "B6"]).rename("MNDWI")

    water = mndwi.gt(0.15)

    water = water.focal_max(1).focal_min(1).focal_mode(2)
    water = water.updateMask(water.connectedPixelCount(500, True).gte(500))
    water = water.clip(offshore_zone.buffer(1000)).rename("water")

    edge = ee.Algorithms.CannyEdgeDetector(
        image=water,
        threshold=0.1,
        sigma=2
    )
    edge = edge.focal_max(1).focal_mode(1).selfMask().rename("shoreline")

    vals = {"NDWI": 0, "MNDWI": 0}

    try:
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
        if stats:
            vals = stats
    except Exception as e:
        print("STATS ERROR:", e)

    return {
        "ndwi": ndwi,
        "mndwi": mndwi,
        "water": water,
        "edge": edge,
        "vals": vals
    }


def calculate_area(mask, band_name, geometry):
    try:
        area_image = ee.Image.pixelArea().updateMask(mask).rename(band_name)
        result = area_image.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=120,
            bestEffort=True,
            tileScale=4,
            maxPixels=1e10
        ).getInfo()
        if result and band_name in result and result[band_name]:
            return round(result[band_name] / 10000, 2)
        return 0
    except Exception as e:
        print("AREA ERROR:", e)
        return 0


def build_layers(aoi, r1, r2):
    erosion = (
        r1["water"].And(r2["water"].Not())
        .rename("erosion")
        .updateMask(r1["water"].And(r2["water"].Not()))
    )

    accretion = (
        r2["water"].And(r1["water"].Not())
        .rename("accretion")
        .updateMask(r2["water"].And(r1["water"].Not()))
    )

    layers = {
        "boundary": get_map_url(
            ee.Image().byte().paint(
                featureCollection=ee.FeatureCollection([ee.Feature(aoi)]),
                color=1,
                width=3
            ),
            {"palette": ["yellow"]}
        ),
        "shoreline1": get_map_url(r1["edge"], {"palette": ["#ff00ff"]}),
        "shoreline2": get_map_url(r2["edge"], {"palette": ["#00ffff"]}),
        "erosion": get_map_url(erosion, {"palette": ["red"]}),
        "accretion": get_map_url(accretion, {"palette": ["lime"]}),
        "ndwi1": get_map_url(
            r1["ndwi"],
            {"min": -0.5, "max": 0.5, "palette": ["brown", "yellow", "green", "cyan", "blue"]}
        ),
        "ndwi2": get_map_url(
            r2["ndwi"],
            {"min": -0.5, "max": 0.5, "palette": ["brown", "yellow", "green", "cyan", "blue"]}
        ),
        "mndwi1": get_map_url(
            r1["mndwi"],
            {"min": -0.5, "max": 0.5, "palette": ["purple", "black", "white", "cyan", "blue"]}
        ),
        "mndwi2": get_map_url(
            r2["mndwi"],
            {"min": -0.5, "max": 0.5, "palette": ["purple", "black", "white", "cyan", "blue"]}
        )
    }

    return layers, erosion, accretion


@app.route("/gee")
def run_analysis():
    try:
        init_gee()

        province = request.args.get("province")
        y1 = request.args.get("y1")
        y2 = request.args.get("y2")

        if not province or not y1 or not y2:
            return jsonify({"error": "Thiếu province, y1 hoặc y2"}), 400

        aoi, offshore_zone = get_region_and_zone(province)
        r1 = get_analysis(offshore_zone, y1)
        r2 = get_analysis(offshore_zone, y2)
        layers, erosion, accretion = build_layers(aoi, r1, r2)

        erosion_ha = calculate_area(erosion, "erosion", offshore_zone)
        accretion_ha = calculate_area(accretion, "accretion", offshore_zone)

        ndwi1 = get_float(r1["vals"], "NDWI")
        mndwi1 = get_float(r1["vals"], "MNDWI")
        ndwi2 = get_float(r2["vals"], "NDWI")
        mndwi2 = get_float(r2["vals"], "MNDWI")

        save_data(province, int(y1), ndwi1, mndwi1, erosion_ha, accretion_ha)
        save_data(province, int(y2), ndwi2, mndwi2, erosion_ha, accretion_ha)

        return jsonify({
            "mode": "gee-style-smooth-coastline",
            "message": "Ranh giới là toàn bộ tỉnh/vùng gộp; đường bờ lấy từ offshore zone giống GEE.",
            "layers": layers,
            "stats": {
                "year1": {"NDWI": ndwi1, "MNDWI": mndwi1},
                "year2": {"NDWI": ndwi2, "MNDWI": mndwi2},
                "erosion_ha": float(erosion_ha),
                "accretion_ha": float(accretion_ha)
            },
            "bounds": safe_bounds(aoi)
        })

    except ValueError as e:
        return jsonify({"error": str(e), "type": type(e).__name__}), 400
    except LookupError as e:
        return jsonify({"error": str(e), "type": type(e).__name__}), 404
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e), "type": type(e).__name__}), 500


@app.route("/gee_heavy")
def gee_heavy():
    try:
        init_gee()

        province = request.args.get("province")
        y1 = request.args.get("y1")
        y2 = request.args.get("y2")
        layer = request.args.get("layer")

        allowed_layers = ["shoreline1", "shoreline2", "erosion", "accretion"]

        if not province or not y1 or not y2 or not layer:
            return jsonify({"error": "Thiếu province, y1, y2 hoặc layer"}), 400
        if layer not in allowed_layers:
            return jsonify({"error": f"Layer không hợp lệ. Chỉ nhận: {', '.join(allowed_layers)}"}), 400

        cache_key = f"{province}_{y1}_{y2}_{layer}_gee_style"
        if cache_key in tile_cache:
            return jsonify({"mode": "advanced-cache", "layer": layer, "layers": {layer: tile_cache[cache_key]}})

        aoi, offshore_zone = get_region_and_zone(province)
        r1 = get_analysis(offshore_zone, y1)
        r2 = get_analysis(offshore_zone, y2)
        layers, erosion, accretion = build_layers(aoi, r1, r2)
        url = layers[layer]
        tile_cache[cache_key] = url

        return jsonify({"mode": "advanced", "layer": layer, "layers": {layer: url}})

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e), "type": type(e).__name__}), 500


@app.route("/forecast")
def forecast():
    province = request.args.get("province")
    if not province:
        return jsonify({"error": "Thiếu province"}), 400

    conn = sqlite3.connect("data/coastal.db")
    df = pd.read_sql_query(
        """
        SELECT *
        FROM coastal_analysis
        WHERE province = ?
        ORDER BY year
        """,
        conn,
        params=(province,)
    )
    conn.close()

    if len(df) < 2:
        return jsonify({"error": "Không đủ dữ liệu"})

    df = (
        df.groupby("year", as_index=False)
        .agg({"erosion": "mean", "accretion": "mean"})
        .sort_values("year")
    )

    if len(df) < 2:
        return jsonify({"error": "Không đủ dữ liệu"})

    X = np.array(df["year"]).reshape(-1, 1)
    y = np.array(df["erosion"])
    model = LinearRegression()
    model.fit(X, y)

    last_year = int(df["year"].max())
    result = []
    for i in range(1, 6):
        year = last_year + i
        pred = model.predict([[year]])[0]
        result.append({"year": year, "prediction": round(float(pred), 2)})

    return jsonify(result)


@app.route("/chat_ai", methods=["POST"])
def chat_ai():
    try:
        if not client:
            return jsonify({"error": "Thiếu GEMINI_API_KEY trong Render Environment"}), 500

        data = request.get_json()
        if not data:
            return jsonify({"error": "Không có dữ liệu gửi lên"}), 400

        prompt = f"""
Tỉnh/vùng nghiên cứu: {data.get('province')}
Dữ liệu thống kê: {data.get('stats')}
Câu hỏi: {data.get('question')}

Hãy trả lời bằng tiếng Việt, có cấu trúc rõ ràng:
1. Nhận xét xói mòn và bồi tụ.
2. Nhận xét NDWI/MNDWI.
3. Dự báo xu hướng đường bờ.
4. Đề xuất giải pháp quản lý ven biển.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        answer = getattr(response, "text", None)

        if not answer:
            return jsonify({"error": "AI không phản hồi"}), 500

        return jsonify({"answer": answer})

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e), "type": type(e).__name__}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
