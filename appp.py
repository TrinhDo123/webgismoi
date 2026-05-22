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

# =========================================================
# FLASK APP
# =========================================================
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


@app.errorhandler(Exception)
def handle_global_exception(e):
    """Luôn trả JSON, tránh frontend nhận HTML Internal Server Error."""
    print("GLOBAL ERROR:")
    print(traceback.format_exc())
    return jsonify({
        "error": str(e),
        "type": type(e).__name__
    }), 500


# =========================================================
# GEMINI AI
# =========================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
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


# =========================================================
# DATABASE
# =========================================================
def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/coastal.db")
    cur = conn.cursor()
    cur.execute("""
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
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO coastal_analysis(province, year, ndwi, mndwi, erosion, accretion)
    VALUES (?, ?, ?, ?, ?, ?)
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


# =========================================================
# GEE INIT - KHÔNG DÙNG ee.Authenticate() TRÊN RENDER
# =========================================================
gee_ready = False
provinces_fc = None

def init_gee():
    global gee_ready, provinces_fc

    if gee_ready:
        return

    info = None

    # Render: dán nguyên JSON service account vào Environment GOOGLE_CREDS_JSON.
    env_json = os.environ.get("GOOGLE_CREDS_JSON", "").strip()
    if env_json:
        try:
            info = json.loads(env_json)
        except json.JSONDecodeError as e:
            raise ValueError(
                "GOOGLE_CREDS_JSON không phải JSON hợp lệ. Hãy dán nguyên nội dung file JSON, không thêm dấu nháy ngoài."
            ) from e
    else:
        # Local: chỉ để test trên máy, tuyệt đối không push file này lên GitHub.
        if not os.path.exists("service_account.json"):
            raise ValueError(
                "Thiếu GOOGLE_CREDS_JSON trên Render Environment hoặc service_account.json khi chạy local."
            )
        with open("service_account.json", "r", encoding="utf-8") as f:
            info = json.load(f)

    for key in ["client_email", "private_key", "project_id"]:
        if key not in info:
            raise ValueError(f"Service account JSON thiếu {key}")

    # Ghi tạm runtime file cho earthengine-api đọc credential.
    with open("/tmp/service_account.json", "w", encoding="utf-8") as f:
        json.dump(info, f)

    credentials = ee.ServiceAccountCredentials(
        info["client_email"],
        "/tmp/service_account.json"
    )

    ee.Initialize(
        credentials,
        project=info["project_id"]
    )

    provinces_fc = (
        ee.FeatureCollection("FAO/GAUL/2015/level1")
        .filter(ee.Filter.eq("ADM0_NAME", "Viet Nam"))
    )

    gee_ready = True


# =========================================================
# TỈNH MỚI / GỘP TỈNH THEO CODE GEE MẪU
# =========================================================
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

non_coastal = {
    "Cao Bang", "Dien Bien", "Lai Chau", "Lang Son", "Son La",
    "Thai Nguyen", "Tuyen Quang", "Lao Cai", "Phu Tho",
    "Bac Ninh", "Dong Nai", "Tay Ninh", "Ha Noi"
}

# Bounds gần đúng để map fit không cần gọi getInfo() nặng.
BOUNDS = {
    "An Giang": [[103.7, 8.4], [106.1, 8.4], [106.1, 11.1], [103.7, 11.1]],
    "Khanh Hoa": [[108.3, 10.4], [109.7, 10.4], [109.7, 13.4], [108.3, 13.4]],
    "Ca Mau": [[104.4, 8.2], [106.2, 8.2], [106.2, 10.2], [104.4, 10.2]],
    "Da Nang": [[107.6, 15.1], [108.9, 15.1], [108.9, 16.4], [107.6, 16.4]],
    "TP Ho Chi Minh": [[106.1, 9.7], [107.7, 9.7], [107.7, 11.4], [106.1, 11.4]],
    "Hai Phong": [[106.2, 20.3], [107.3, 20.3], [107.3, 21.2], [106.2, 21.2]],
    "Quang Ninh": [[106.5, 20.5], [108.2, 20.5], [108.2, 21.7], [106.5, 21.7]],
    "Vinh Long": [[105.2, 9.3], [106.9, 9.3], [106.9, 10.5], [105.2, 10.5]]
}
DEFAULT_BOUNDS = [[102.0, 8.0], [110.0, 8.0], [110.0, 23.5], [102.0, 23.5]]


def get_selected(province):
    if province in non_coastal:
        raise ValueError(f"Tỉnh {province} không giáp biển")

    selected = next((d for d in coastal_data if d["label"] == province), None)
    if not selected:
        raise LookupError(f"Không tìm thấy cấu hình tỉnh {province}")
    return selected


def get_region_and_zone(province):
    """
    Làm giống GEE mẫu:
    - aoi: toàn bộ tỉnh/vùng gộp -> vẽ ranh giới vàng.
    - offshore_zone: phần buffer nằm ngoài aoi -> lấy NDWI/MNDWI/đường bờ.
    Không gọi size().getInfo() để tránh Render timeout/OOM.
    """
    selected = get_selected(province)
    region = provinces_fc.filter(ee.Filter.inList("ADM1_NAME", selected["search"]))
    aoi = region.geometry().dissolve()

    coastal_buffer = aoi.buffer(2000)
    offshore_zone = coastal_buffer.difference(aoi, 1).intersection(aoi.bounds(), 1)
    return aoi, offshore_zone


def get_map_url(image, vis):
    return image.getMapId(vis)["tile_fetcher"].url_format


def get_analysis(offshore_zone, year):
    """
    Nhẹ hơn bản cũ để tránh Render 500:
    - Không dùng connectedPixelCount lớn.
    - Không reduceRegion trong bước tạo layer.
    - Đường bờ được làm mượt bằng focal + Canny như GEE mẫu.
    """
    l8 = ee.ImageCollection("LANDSAT/LC08/C02/T1_TOA")
    l9 = ee.ImageCollection("LANDSAT/LC09/C02/T1_TOA")

    collection = (
        l8.merge(l9)
        .filterBounds(offshore_zone)
        .filterDate(f"{year}-01-01", f"{year}-12-31")
        .filter(ee.Filter.lt("CLOUD_COVER", 45))
        .sort("CLOUD_COVER")
        .limit(12)
    )

    img = collection.median().clip(offshore_zone)

    ndwi = img.normalizedDifference(["B3", "B5"]).rename("NDWI")
    mndwi = img.normalizedDifference(["B3", "B6"]).rename("MNDWI")

    water = mndwi.gt(0.15)
    water = water.focal_max(1).focal_min(1).focal_mode(1).rename("water")

    edge = ee.Algorithms.CannyEdgeDetector(
        image=water,
        threshold=0.1,
        sigma=2
    )
    edge = edge.focal_max(1).selfMask().rename("shoreline")

    return {
        "ndwi": ndwi,
        "mndwi": mndwi,
        "water": water,
        "edge": edge
    }


def safe_reduce_mean(image, geometry):
    """Reduce rất thô. Nếu EE chậm/lỗi thì trả 0 để không chết app."""
    try:
        result = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=1000,
            bestEffort=True,
            tileScale=2,
            maxPixels=1e7
        ).getInfo()
        return result or {}
    except Exception as e:
        print("STATS ERROR:", e)
        return {}


def safe_area(mask, band_name, geometry):
    """Tính diện tích thô. Có lỗi thì trả 0 để tránh HTTP 500."""
    try:
        area_img = ee.Image.pixelArea().updateMask(mask).rename(band_name)
        result = area_img.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=1000,
            bestEffort=True,
            tileScale=2,
            maxPixels=1e7
        ).getInfo()
        value = result.get(band_name, 0) if result else 0
        return round(float(value or 0) / 10000, 2)
    except Exception as e:
        print("AREA ERROR:", e)
        return 0.0


def float_or_zero(v):
    try:
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def build_layers(aoi, r1, r2):
    erosion = (
        r1["water"].And(r2["water"].Not())
        .rename("erosion")
        .selfMask()
    )
    accretion = (
        r2["water"].And(r1["water"].Not())
        .rename("accretion")
        .selfMask()
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

        province = request.args.get("province", "").strip()
        y1 = request.args.get("y1", "").strip()
        y2 = request.args.get("y2", "").strip()

        if not province or not y1 or not y2:
            return jsonify({"error": "Thiếu province, y1 hoặc y2"}), 400

        aoi, offshore_zone = get_region_and_zone(province)

        r1 = get_analysis(offshore_zone, y1)
        r2 = get_analysis(offshore_zone, y2)
        layers, erosion, accretion = build_layers(aoi, r1, r2)

        stats1 = safe_reduce_mean(r1["ndwi"].addBands(r1["mndwi"]), offshore_zone)
        stats2 = safe_reduce_mean(r2["ndwi"].addBands(r2["mndwi"]), offshore_zone)

        ndwi1 = float_or_zero(stats1.get("NDWI", 0))
        mndwi1 = float_or_zero(stats1.get("MNDWI", 0))
        ndwi2 = float_or_zero(stats2.get("NDWI", 0))
        mndwi2 = float_or_zero(stats2.get("MNDWI", 0))

        erosion_ha = safe_area(erosion, "erosion", offshore_zone)
        accretion_ha = safe_area(accretion, "accretion", offshore_zone)

        # Lưu DB nhưng lỗi DB không được làm chết API.
        try:
            save_data(province, int(y1), ndwi1, mndwi1, erosion_ha, accretion_ha)
            save_data(province, int(y2), ndwi2, mndwi2, erosion_ha, accretion_ha)
        except Exception as db_error:
            print("DB SAVE ERROR:", db_error)

        return jsonify({
            "mode": "gee-style-stable",
            "message": "Ranh giới là toàn bộ tỉnh/vùng gộp; đường bờ lấy từ offshore zone giống GEE.",
            "layers": layers,
            "stats": {
                "year1": {"NDWI": ndwi1, "MNDWI": mndwi1},
                "year2": {"NDWI": ndwi2, "MNDWI": mndwi2},
                "erosion_ha": float(erosion_ha),
                "accretion_ha": float(accretion_ha)
            },
            "bounds": BOUNDS.get(province, DEFAULT_BOUNDS)
        })

    except ValueError as e:
        return jsonify({"error": str(e), "type": type(e).__name__}), 400
    except LookupError as e:
        return jsonify({"error": str(e), "type": type(e).__name__}), 404
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e), "type": type(e).__name__}), 500


@app.route("/forecast")
def forecast():
    province = request.args.get("province", "").strip()
    if not province:
        return jsonify({"error": "Thiếu province"}), 400

    try:
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

        df = df.groupby("year", as_index=False).agg({"erosion": "mean"}).sort_values("year")
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

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e), "type": type(e).__name__}), 500


@app.route("/chat_ai", methods=["POST"])
def chat_ai():
    try:
        if not client:
            return jsonify({"error": "Thiếu GEMINI_API_KEY trong Render Environment"}), 500

        data = request.get_json(silent=True)
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
