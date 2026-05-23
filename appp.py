import os
import json
import sqlite3
import traceback

import ee
import numpy as np
import pandas as pd

from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
from sklearn.linear_model import LinearRegression
from google import genai


# =========================
# FLASK APP
# =========================
app = Flask(__name__)

CORS(app, resources={
    r"/*": {
        "origins": "*"
    }
})


@app.errorhandler(Exception)
def handle_global_exception(e):
    print("GLOBAL ERROR:")
    print(traceback.format_exc())

    return jsonify({
        "error": str(e),
        "type": type(e).__name__
    }), 500


# =========================
# GEMINI AI
# =========================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

client = None

if GEMINI_API_KEY:
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )


# =========================
# HOME ROUTE - MỞ GIAO DIỆN WEBGIS
# =========================
@app.route("/")
def index():
    return render_template("index.html")


# =========================
# HEALTH ROUTE - TEST API
# =========================
@app.route("/health")
def health():
    return jsonify({
        "status": "WebGIS API is running",
        "gee_test": "/gee?province=Da%20Nang&y1=2020&y2=2024",
        "gee_heavy_test": "/gee_heavy?province=Da%20Nang&y1=2020&y2=2024&layer=shoreline1",
        "forecast_test": "/forecast?province=Da%20Nang",
        "chat_ai": "/chat_ai"
    })


# =========================
# SERVE STATIC FILES
# =========================
@app.route("/appp.js")
def serve_js():
    return send_from_directory(
        os.getcwd(),
        "appp.js"
    )


@app.route("/style.css")
def serve_css():
    return send_from_directory(
        os.getcwd(),
        "style.css"
    )


# =========================
# DATABASE
# =========================
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
    INSERT INTO coastal_analysis(
        province,
        year,
        ndwi,
        mndwi,
        erosion,
        accretion
    )
    VALUES(?,?,?,?,?,?)
    """, (
        province,
        year,
        ndwi,
        mndwi,
        erosion,
        accretion
    ))

    conn.commit()

    conn.close()


# =========================
# INIT GEE - LAZY LOAD
# =========================
gee_ready = False

provinces_fc = None
gsw = None
permanent_water = None

tile_cache = {}


def init_gee():

    global gee_ready
    global provinces_fc
    global gsw
    global permanent_water

    if gee_ready:
        return

    info = None

    # Ưu tiên dùng ENV trên Render
    if os.environ.get("GOOGLE_CREDS_JSON"):

        try:
            info = json.loads(
                os.environ["GOOGLE_CREDS_JSON"]
            )

        except json.JSONDecodeError as e:
            raise ValueError(
                "GOOGLE_CREDS_JSON không phải JSON hợp lệ. Hãy copy nguyên nội dung file JSON service account vào Render Environment."
            ) from e

        with open("service_account.json", "w", encoding="utf-8") as f:
            json.dump(info, f)

    # Nếu chạy local thì dùng file service_account.json
    else:

        if not os.path.exists("service_account.json"):
            raise FileNotFoundError(
                "Không tìm thấy service_account.json hoặc GOOGLE_CREDS_JSON trên Render"
            )

        with open("service_account.json", "r", encoding="utf-8") as f:
            info = json.load(f)

    # Kiểm tra key bắt buộc
    if not info:
        raise ValueError(
            "Không đọc được thông tin service account"
        )

    if "client_email" not in info:
        raise ValueError(
            "service_account.json thiếu client_email"
        )

    if "private_key" not in info:
        raise ValueError(
            "service_account.json thiếu private_key"
        )

    if "project_id" not in info:
        raise ValueError(
            "service_account.json thiếu project_id"
        )

    service_account = info["client_email"]
    project_id = info["project_id"]

    credentials = ee.ServiceAccountCredentials(
        service_account,
        "service_account.json"
    )

    try:
        ee.Initialize(
            credentials,
            project=project_id
        )

    except TypeError:
        ee.Initialize(credentials)

    provinces_fc = (
        ee.FeatureCollection(
            "FAO/GAUL/2015/level1"
        )
        .filter(
            ee.Filter.eq(
                "ADM0_NAME",
                "Viet Nam"
            )
        )
    )

    gsw = ee.Image(
        "JRC/GSW1_4/GlobalSurfaceWater"
    )

    permanent_water = (
        gsw
        .select("occurrence")
        .gt(80)
    )

    gee_ready = True


# Chỉ init database khi start app
# Không init Earth Engine ở đây để tránh Render timeout port
init_db()


# =========================
# DATA
# =========================
coastal_data = [

    {"label": "An Giang", "search": ["Kien Giang", "An Giang"], "coast": ["Kien Giang"]},
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
    "Cao Bang",
    "Dien Bien",
    "Lai Chau",
    "Lang Son",
    "Son La",
    "Thai Nguyen",
    "Tuyen Quang",
    "Lao Cai",
    "Phu Tho",
    "Bac Ninh",
    "Dong Nai",
    "Tay Ninh",
    "Ha Noi"
]


# =========================
# GEE HELPERS
# =========================
def get_selected(province):

    selected = next(
        (
            d for d in coastal_data
            if d["label"] == province
        ),
        None
    )

    if not selected:
        raise ValueError(
            f"Tỉnh {province} không giáp biển hoặc chưa cấu hình vùng bờ biển"
        )

    return selected

def get_region_and_zone(province):

    selected = get_selected(province)

    # 1. Vùng đầy đủ: dùng để vẽ ranh giới tỉnh/vùng nghiên cứu
    region = provinces_fc.filter(
        ee.Filter.inList(
            "ADM1_NAME",
            selected["search"]
        )
    )

    count_region = region.size().getInfo()

    if count_region == 0:
        raise LookupError(
            f"Không tìm thấy ranh giới GEE cho {province}"
        )

    aoi = (
        region
        .geometry()
        .dissolve()
    )

    # 2. NDWI/MNDWI chỉ hiện thành dải quanh ranh giới, không phủ toàn tỉnh
    # NDWI/MNDWI chỉ hiện thành dải quanh mép ranh giới, không phủ toàn bộ tỉnh
    outer_band = aoi.buffer(3000)

    inner_band = aoi.buffer(-3000)

    index_zone = (
            outer_band
            .difference(
                inner_band,
                1
            )
            .intersection(
                aoi,
                1
            )
        )

    # 3. Vùng thật sự có biển: dùng riêng cho đường bờ/xói mòn/bồi tụ
    coast_names = selected.get(
        "coast",
        selected["search"]
    )

    coast_region = provinces_fc.filter(
        ee.Filter.inList(
            "ADM1_NAME",
            coast_names
        )
    )

    count_coast = coast_region.size().getInfo()

    if count_coast == 0:
        raise LookupError(
            f"Không tìm thấy vùng ven biển cho {province}"
        )

    coast_aoi = (
        coast_region
        .geometry()
        .dissolve()
    )

    # Toàn bộ phần đất Việt Nam để loại bỏ đất liền
    vietnam_land = (
        provinces_fc
        .geometry()
        .dissolve()
    )

    # Chỉ lấy vùng ngoài biển, sát vùng ven biển
    offshore_zone = (
        coast_aoi
        .buffer(1000)
        .difference(
            vietnam_land,
            1
        )
        .intersection(
            coast_aoi.bounds(),
            1
        )
    )

    return aoi, index_zone, offshore_zone
def safe_bounds(aoi):

    try:
        return aoi.bounds().getInfo()["coordinates"][0]

    except Exception as e:
        print("BOUNDS ERROR:", e)

        return [
            [108.0, 16.0],
            [109.0, 16.0],
            [109.0, 17.0],
            [108.0, 17.0],
            [108.0, 16.0]
        ]


def get_map_url(image, vis_params):

    return image.getMapId(
        vis_params
    )["tile_fetcher"].url_format


# =========================
# CLOUD MASK
# =========================
def mask_l8_sr(image):

    qa = image.select("QA_PIXEL")

    cloud = qa.bitwiseAnd(1 << 3).eq(0)

    shadow = qa.bitwiseAnd(1 << 4).eq(0)

    mask = cloud.And(shadow)

    optical = (
        image.select([
            "SR_B2",
            "SR_B3",
            "SR_B4",
            "SR_B5",
            "SR_B6",
            "SR_B7"
        ])
        .multiply(0.0000275)
        .add(-0.2)
    )

    return (
        optical
        .updateMask(mask)
        .copyProperties(
            image,
            image.propertyNames()
        )
    )


# =========================
# GET ANALYSIS - OPTIMIZED FOR RENDER
# =========================
def get_analysis(offshore_zone, year, include_heavy=False):

    dataset = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(offshore_zone)
        .filterDate(
            f"{year}-01-01",
            f"{year}-12-31"
        )
        .filter(
            ee.Filter.lt(
                "CLOUD_COVER",
                70
            )
        )
        .sort("CLOUD_COVER")
        .map(mask_l8_sr)
        .limit(6)
    )

    count = dataset.size().getInfo()

    if count == 0:
        raise Exception(
            f"Không có ảnh Landsat cho năm {year}. Hãy thử năm khác."
        )

    img = (
        dataset
        .median()
        .clip(offshore_zone)
    )

    green = img.select("SR_B3")
    nir = img.select("SR_B5")
    swir = img.select("SR_B6")

    ndwi = (
        green.subtract(nir)
        .divide(green.add(nir))
        .rename("NDWI")
    )

    mndwi = (
        green.subtract(swir)
        .divide(green.add(swir))
        .rename("MNDWI")
    )

    vals = {
        "NDWI": 0,
        "MNDWI": 0
    }

    try:
        stats = (
            ndwi.addBands(mndwi)
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=offshore_zone,
                scale=300,
                bestEffort=True,
                tileScale=16,
                maxPixels=1e8
            )
            .getInfo()
        )

        if stats:
            vals["NDWI"] = float(stats.get("NDWI", 0) or 0)
            vals["MNDWI"] = float(stats.get("MNDWI", 0) or 0)

    except Exception as e:
        print("STATS ERROR:", e)

        result = {
            "ndwi": ndwi,
            "mndwi": mndwi,
            "vals": vals
        }

    if include_heavy:

        # Chỉ giữ nước thật ngoài biển.
        # Hạn chế lấy ruộng, ao, hồ, sông/rạch nhỏ trong đất liền.
        water = (
            mndwi
            .gt(0.10)
            .And(
                permanent_water
            )
        )

        water = (
            water
            .focal_max(1)
            .focal_min(1)
            .focal_mode(1)
        )

        water = water.updateMask(
            water.connectedPixelCount(
                150,
                True
            ).gte(150)
        )

        edge = (
            ee.Algorithms.CannyEdgeDetector(
                image=water,
                threshold=0.08,
                sigma=1.8
            )
            .focal_max(1)
            .selfMask()
        )

        result["water"] = water.rename("water")
        result["edge"] = edge.rename("shoreline")

    return result



def calculate_area(mask, band_name, geometry):

    try:

        area_image = (
            ee.Image.pixelArea()
            .updateMask(mask)
            .rename(band_name)
        )

        result = area_image.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=500,
            bestEffort=True,
            tileScale=16,
            maxPixels=1e8
        ).getInfo()

        if (
            result and
            band_name in result and
            result[band_name]
        ):

            return round(
                result[band_name] / 10000,
                2
            )

        return 0

    except Exception as e:

        print("AREA ERROR:", e)

        return 0


# =========================
# API GEE - LIGHT MODE
# =========================
@app.route("/gee")
def run_analysis():

    try:

        init_gee()

        province = request.args.get("province")
        y1 = request.args.get("y1")
        y2 = request.args.get("y2")

        if not province or not y1 or not y2:

            return jsonify({
                "error": "Thiếu province, y1 hoặc y2"
            }), 400

        aoi, index_zone, offshore_zone = get_region_and_zone(
            province
        )

# NDWI/MNDWI tính theo toàn vùng ranh giới để hiển thị giống ranh giới tỉnh
        r1 = get_analysis(
            index_zone,
            y1,
            include_heavy=False
        )

        r2 = get_analysis(
            index_zone,
            y2,
            include_heavy=False
        )

        # Đường bờ/xói mòn/bồi tụ chỉ tính ngoài biển
        h1 = get_analysis(
            offshore_zone,
            y1,
            include_heavy=True
        )

        h2 = get_analysis(
            offshore_zone,
            y2,
            include_heavy=True
        )

        erosion = (
            h1["water"]
            .And(
                h2["water"].Not()
            )
            .rename("erosion")
            .selfMask()
        )

        accretion = (
            h2["water"]
            .And(
                h1["water"].Not()
            )
            .rename("accretion")
            .selfMask()
        )

        erosion_ha = calculate_area(
            erosion,
            "erosion",
            offshore_zone
        )

        accretion_ha = calculate_area(
            accretion,
            "accretion",
            offshore_zone
        )

        save_data(
            province,
            int(y2),
            float(r2["vals"].get("NDWI", 0) or 0),
            float(r2["vals"].get("MNDWI", 0) or 0),
            erosion_ha,
            accretion_ha
    )

        bounds = safe_bounds(aoi)

        result = {

            "mode": "light",

            "message": "Đã tải lớp cơ bản. Bấm chọn Đường bờ / Xói mòn / Bồi tụ để tải lớp nâng cao.",

            "layers": {

                "boundary":
                get_map_url(
                    ee.Image()
                    .byte()
                    .paint(
                        featureCollection=ee.FeatureCollection([
                            ee.Feature(aoi)
                        ]),
                        color=1,
                        width=3
                    ),
                    {
                        "palette": ["yellow"]
                    }
                ),

                "ndwi1":
                get_map_url(
                    r1["ndwi"],
                    {
                        "min": -1,
                        "max": 1,
                        "palette": [
                            "white",
                            "blue"
                        ]
                    }
                ),

                "ndwi2":
                get_map_url(
                    r2["ndwi"],
                    {
                        "min": -1,
                        "max": 1,
                        "palette": [
                            "white",
                            "blue"
                        ]
                    }
                ),

                "mndwi1":
                get_map_url(
                    r1["mndwi"],
                    {
                        "min": -1,
                        "max": 1,
                        "palette": [
                            "white",
                            "green"
                        ]
                    }
                ),

                "mndwi2":
                get_map_url(
                    r2["mndwi"],
                    {
                        "min": -1,
                        "max": 1,
                        "palette": [
                            "white",
                            "green"
                        ]
                    }
                )
            },

            "stats": {

                "year1": {
                    "NDWI": float(r1["vals"].get("NDWI", 0) or 0),
                    "MNDWI": float(r1["vals"].get("MNDWI", 0) or 0)
                },

                "year2": {
                    "NDWI": float(r2["vals"].get("NDWI", 0) or 0),
                    "MNDWI": float(r2["vals"].get("MNDWI", 0) or 0)
                },

                "erosion_ha": float(erosion_ha),

                "accretion_ha": float(accretion_ha)
            },

            "bounds": bounds
        }

        return jsonify(result)

    except ValueError as e:

        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        }), 400

    except LookupError as e:

        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        }), 404

    except Exception as e:

        print(traceback.format_exc())

        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        }), 500


# =========================
# API GEE - ADVANCED SINGLE LAYER
# =========================
@app.route("/gee_heavy")
def gee_heavy():

    try:

        init_gee()

        province = request.args.get("province")
        y1 = request.args.get("y1")
        y2 = request.args.get("y2")
        layer = request.args.get("layer")

        allowed_layers = [
            "shoreline1",
            "shoreline2",
            "erosion",
            "accretion"
        ]

        if not province or not y1 or not y2 or not layer:

            return jsonify({
                "error": "Thiếu province, y1, y2 hoặc layer"
            }), 400

        if layer not in allowed_layers:

            return jsonify({
                "error": f"Layer không hợp lệ. Chỉ nhận: {', '.join(allowed_layers)}"
            }), 400

        cache_key = f"{province}_{y1}_{y2}_{layer}"

        if cache_key in tile_cache:

            return jsonify({
                "mode": "advanced-cache",
                "layer": layer,
                "layers": {
                    layer: tile_cache[cache_key]
                }
            })

        aoi, index_zone, offshore_zone = get_region_and_zone(
    province
)
        if layer == "shoreline1":

            r1 = get_analysis(offshore_zone, y1, include_heavy=True)

            url = get_map_url(
                r1["edge"],
                {
                    "palette": ["#ff00ff"]
                }
            )

        elif layer == "shoreline2":

            r2 = get_analysis(offshore_zone, y2, include_heavy=True)


            url = get_map_url(
                r2["edge"],
                {
                    "palette": ["#00ffff"]
                }
            )

        elif layer in ["erosion", "accretion"]:

            r1 = get_analysis(
                offshore_zone,
                y1,
                include_heavy=True
            )

            r2 = get_analysis(
                offshore_zone,
                y2,
                include_heavy=True
            )

            erosion = r1["water"].And(r2["water"].Not()).selfMask()

            accretion = r2["water"].And(r1["water"].Not()).selfMask()

            if layer == "erosion":

                url = get_map_url(
                    erosion,
                    {
                        "palette": ["red"]
                    }
                )

            else:

                url = get_map_url(
                    accretion,
                    {
                        "palette": ["lime"]
                    }
                )

        tile_cache[cache_key] = url

        return jsonify({
            "mode": "advanced",
            "layer": layer,
            "layers": {
                layer: url
            }
        })

    except ValueError as e:

        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        }), 400

    except LookupError as e:

        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        }), 404

    except Exception as e:

        print(traceback.format_exc())

        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        }), 500


# =========================
# FORECAST AI
# =========================
@app.route("/forecast")
def forecast():

    province = request.args.get("province")

    if not province:

        return jsonify({
            "error": "Thiếu province"
        }), 400

    conn = sqlite3.connect(
        "data/coastal.db"
    )

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

        return jsonify({
            "error": "Không đủ dữ liệu"
        })

    X = np.array(df["year"]).reshape(-1, 1)

    y = np.array(df["erosion"])

    model = LinearRegression()

    model.fit(X, y)

    last_year = int(df["year"].max())

    result = []

    for i in range(1, 6):

        year = last_year + i

        pred = model.predict([[year]])[0]

        result.append({
            "year": year,
            "prediction": round(float(pred), 2)
        })

    return jsonify(result)


# =========================
# CHAT AI GIS - CÓ FALLBACK KHI GEMINI QUÁ TẢI
# =========================
def build_local_ai_answer(province, stats, question):
    stats = stats or {}
    year1 = stats.get("year1", {}) or {}
    year2 = stats.get("year2", {}) or {}

    ndwi1 = float(year1.get("NDWI", 0) or 0)
    mndwi1 = float(year1.get("MNDWI", 0) or 0)
    ndwi2 = float(year2.get("NDWI", 0) or 0)
    mndwi2 = float(year2.get("MNDWI", 0) or 0)

    erosion = float(stats.get("erosion_ha", 0) or 0)
    accretion = float(stats.get("accretion_ha", 0) or 0)

    avg_ndwi = (ndwi1 + ndwi2) / 2
    avg_mndwi = (mndwi1 + mndwi2) / 2

    if erosion > accretion:
        trend = (
            "Khu vực có xu hướng xói mòn mạnh hơn bồi tụ. "
            "Điều này cho thấy đường bờ có nguy cơ bị thu hẹp hoặc mất ổn định."
        )
    elif accretion > erosion:
        trend = (
            "Khu vực có xu hướng bồi tụ mạnh hơn xói mòn. "
            "Điều này cho thấy quá trình tích tụ trầm tích đang chiếm ưu thế."
        )
    else:
        trend = (
            "Khu vực tương đối cân bằng giữa xói mòn và bồi tụ, "
            "hoặc dữ liệu hiện tại chưa cho thấy chênh lệch lớn."
        )

    if avg_ndwi < -0.3:
        ndwi_text = "NDWI thấp, tín hiệu nước mặt yếu, khu vực chủ yếu là đất hoặc bề mặt khô."
    elif avg_ndwi <= 0.3:
        ndwi_text = "NDWI trung bình, thể hiện vùng chuyển tiếp giữa đất và nước hoặc vùng ẩm ven biển."
    else:
        ndwi_text = "NDWI cao, cho thấy tín hiệu nước mặt rõ rệt."

    if avg_mndwi < -0.3:
        mndwi_text = "MNDWI thấp, khả năng nhận diện nước mặt không rõ."
    elif avg_mndwi <= 0.3:
        mndwi_text = "MNDWI trung bình, phù hợp với vùng đất ngập nước, cửa sông hoặc ven biển."
    else:
        mndwi_text = "MNDWI cao, phản ánh vùng nước mặt rõ ràng."

    answer = f"""
PHÂN TÍCH AI VEN BIỂN

Khu vực nghiên cứu: {province}

Câu hỏi của bạn: {question}

1. Nhận xét chung:
{trend}

2. Chỉ số NDWI:
- NDWI năm đầu: {ndwi1:.4f}
- NDWI năm sau: {ndwi2:.4f}
- Nhận xét: {ndwi_text}

3. Chỉ số MNDWI:
- MNDWI năm đầu: {mndwi1:.4f}
- MNDWI năm sau: {mndwi2:.4f}
- Nhận xét: {mndwi_text}

4. Biến động diện tích:
- Xói mòn: {erosion:.2f} ha
- Bồi tụ: {accretion:.2f} ha

5. Khuyến nghị:
- Theo dõi ảnh vệ tinh định kỳ để cập nhật biến động đường bờ.
- Ưu tiên kiểm tra thực địa tại các đoạn bờ có xói mòn cao.
- Kết hợp dữ liệu sóng, thủy triều, dòng chảy, rừng ngập mặn và hoạt động khai thác ven biển.
- Dùng kết quả WebGIS như công cụ hỗ trợ cảnh báo sớm, không thay thế hoàn toàn khảo sát thực địa.

Ghi chú: Câu trả lời này được tạo bằng bộ phân tích nội bộ khi Gemini đang quá tải, thiếu API key hoặc tạm thời không phản hồi.
"""
    return answer.strip()


@app.route("/chat_ai", methods=["POST"])
def chat_ai():

    try:
        data = request.get_json(silent=True)

        if not data:
            return jsonify({
                "answer": "Không có dữ liệu gửi lên để phân tích.",
                "source": "local"
            })

        province = data.get("province", "Không rõ")
        stats = data.get("stats", {}) or {}
        question = data.get("question", "") or ""

        local_answer = build_local_ai_answer(
            province,
            stats,
            question
        )

        if not client:
            return jsonify({
                "answer": local_answer,
                "source": "local",
                "warning": "Thiếu GEMINI_API_KEY nên hệ thống dùng phân tích nội bộ."
            })

        prompt = f"""
Bạn là trợ lý GIS và viễn thám.

Yêu cầu bắt buộc:
- Chỉ trả lời đúng câu hỏi người dùng hỏi.
- Không tự viết thêm phần không liên quan.
- Không tự giới thiệu lại thông tin tỉnh nếu người dùng không hỏi.
- Không viết báo cáo dài nếu người dùng chỉ hỏi ngắn.
- Nếu câu hỏi hỏi "ở đâu", chỉ trả lời vị trí/khu vực.
- Nếu câu hỏi hỏi "vì sao", chỉ giải thích nguyên nhân.
- Nếu câu hỏi hỏi "xu hướng", chỉ phân tích xu hướng.
- Nếu câu hỏi hỏi "so sánh", chỉ tập trung so sánh.
- Nếu câu hỏi hỏi "dự báo", chỉ tập trung vào dự báo.
- Nếu câu hỏi hỏi "khuyến nghị", chỉ tập trung vào khuyến nghị.
- Nếu câu hỏi hỏi "NDWI/MNDWI", chỉ tập trung vào phân tích NDWI/MNDWI.
- Nếu câu hỏi hỏi "biến động", chỉ tập trung vào phân tích biến động.
- Nếu câu hỏi hỏi "điều kiện", chỉ tập trung vào phân tích điều kiện hiện tại.
- Nếu câu hỏi hỏi "giải pháp", chỉ tập trung vào đề xuất giải pháp.
- Nếu câu hỏi hỏi "thực địa", chỉ tập trung vào khuyến nghị thực địa.
- Nếu câu hỏi hỏi "theo dõi", chỉ tập trung vào khuyến nghị theo dõi.
- Nếu câu hỏi hỏi "cảnh báo", chỉ tập trung vào khuyến nghị cảnh báo.
- Nếu câu hỏi hỏi "xói mòn/bồi tụ", chỉ tập trung vào phân tích xói mòn và bồi tụ.
- Nếu câu hỏi hỏi "ảnh hưởng", chỉ tập trung vào phân tích .
- Nếu câu hỏi hỏi "xói mòn", chỉ tập trung vào xói mòn.
- Nếu câu hỏi hỏi "bồi tụ", chỉ tập trung vào bồi tụ.
- Trả lời bằng tiếng Việt, ngắn gọn, rõ ràng.

Dữ liệu hiện có:
Tỉnh/vùng nghiên cứu: {province}
Thống kê: {stats}

Câu hỏi người dùng:
{question}

Hãy trả lời trực tiếp câu hỏi trên.
"""

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            answer = getattr(response, "text", None)

            if answer:
                return jsonify({
                    "answer": answer,
                    "source": "gemini"
                })

            return jsonify({
                "answer": local_answer,
                "source": "local",
                "warning": "Gemini không trả về nội dung nên dùng phân tích nội bộ."
            })

        except Exception as gemini_error:
            print("GEMINI ERROR:")
            print(traceback.format_exc())

            return jsonify({
                "answer": local_answer,
                "source": "local",
                "warning": str(gemini_error)
            })

    except Exception as e:
        print(traceback.format_exc())

        return jsonify({
            "answer": "AI nội bộ không thể xử lý câu hỏi lúc này. Hãy chạy lại phân tích hoặc thử câu hỏi ngắn hơn.",
            "source": "local",
            "warning": str(e)
        })

# =========================
# RUN LOCAL
# =========================
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )