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
ocean_mask = None

tile_cache = {}


def init_gee():

    global gee_ready
    global provinces_fc
    global gsw
    global permanent_water
    global ocean_mask

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

    # Mặt nạ biển thật: độ cao đáy biển < 0 m.
    # Dùng để loại bỏ sông, ao hồ, đầm nuôi trong đất liền.
    ocean_mask = (
        ee.Image("NOAA/NGDC/ETOPO1")
        .select("bedrock")
        .lt(0)
        .rename("ocean")
    )

    gee_ready = True


# Chỉ init database khi start app
# Không init Earth Engine ở đây để tránh Render timeout port
init_db()


# =========================
# DATA - CHỈ GIỮ TỈNH/VÙNG GIÁP BIỂN THẬT
# Không map tỉnh không giáp biển sang tỉnh khác.
# =========================
ccoastal_data = [

    {"label": "Ca Mau", "search": ["Bac Lieu", "Ca Mau"]},
    {"label": "Ha Tinh", "search": ["Ha Tinh"]},
    {"label": "Khanh Hoa", "search": ["Khanh Hoa", "Ninh Thuan"]},
    {"label": "Nghe An", "search": ["Nghe An"]},
    {"label": "Quang Ngai", "search": ["Quang Ngai", "Kon Tum"]},
    {"label": "Quang Ninh", "search": ["Quang Ninh"]},
    {"label": "Quang Tri", "search": ["Quang Binh", "Quang Tri"]},
    {"label": "Thanh Hoa", "search": ["Thanh Hoa"]},
    {"label": "Da Nang", "search": ["Quang Nam", "Da Nang"]},
    {"label": "Hai Phong", "search": ["Hai Duong", "Hai Phong"]},
    {"label": "TP Ho Chi Minh", "search": ["Binh Duong", "Ho Chi Minh", "Ba Ria"]},
    {"label": "Hue", "search": ["Thua Thien Hue"]},
    {"label": "Vinh Long", "search": ["Ben Tre", "Vinh Long", "Tra Vinh"]}

]

non_coastal = []


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
            f"Tỉnh {province} không giáp biển hoặc chưa được cấu hình vùng bờ biển"
        )

    return selected


def get_region_and_zone(province):

    selected = get_selected(province)

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

    coastal_buffer = aoi.buffer(2000)

    offshore_zone = (
        coastal_buffer
        .difference(aoi, 1)
        .intersection(
            aoi.bounds(),
            1
        )
    )

    return aoi, offshore_zone

def get_coastal_masks(aoi, search_zone):
    """
    Tạo mask dải ven biển thật:
    - land_mask: đất thuộc tỉnh
    - sea_mask: biển thật theo ETOPO1 bedrock < 0
    - coast_strip: chỉ những pixel nằm gần cả đất của tỉnh và biển thật
    - coast_core: lõi sát đường tiếp xúc đất/nước để vẽ shoreline
    Cách này loại bỏ biên giới đất liền, sông, hồ, đầm nuôi tôm trong nội địa.
    """

    land_mask = (
        ee.Image.constant(1)
        .clip(aoi)
        .rename("land")
        .unmask(0)
        .gt(0)
    )

    sea_mask = (
        ocean_mask
        .clip(search_zone)
        .selfMask()
    )

    near_sea_5000 = (
        sea_mask
        .focal_max(radius=5000, units="meters")
        .unmask(0)
        .gt(0)
    )

    near_land_5000 = (
        land_mask
        .focal_max(radius=5000, units="meters")
        .unmask(0)
        .gt(0)
    )

    near_sea_1800 = (
        sea_mask
        .focal_max(radius=1800, units="meters")
        .unmask(0)
        .gt(0)
    )

    near_land_1800 = (
        land_mask
        .focal_max(radius=1800, units="meters")
        .unmask(0)
        .gt(0)
    )

    coast_strip = (
        near_sea_5000
        .And(near_land_5000)
        .selfMask()
        .rename("coast_strip")
    )

    coast_core = (
        near_sea_1800
        .And(near_land_1800)
        .selfMask()
        .rename("coast_core")
    )

    coast_boundary = (
        ee.Algorithms.CannyEdgeDetector(
            image=land_mask,
            threshold=0.1,
            sigma=1
        )
        .updateMask(coast_core)
        .selfMask()
        .rename("coast_boundary")
    )

    return {
        "land_mask": land_mask,
        "sea_mask": sea_mask,
        "coast_strip": coast_strip,
        "coast_core": coast_core,
        "coast_boundary": coast_boundary
    }


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
        ee.ImageCollection(
            "LANDSAT/LC08/C02/T1_TOA"
        )
        .filterBounds(offshore_zone)
        .filterDate(
            f"{year}-01-01",
            f"{year}-12-31"
        )
        .filter(
            ee.Filter.lt(
                "CLOUD_COVER",
                25
            )
        )
    )

    img = (
        dataset
        .median()
        .clip(offshore_zone)
    )

    ndwi = (
        img.normalizedDifference([
            "B3",
            "B5"
        ])
        .rename("NDWI")
    )

    mndwi = (
        img.normalizedDifference([
            "B3",
            "B6"
        ])
        .rename("MNDWI")
    )

    water = mndwi.gt(0.15)

    water = (
        water
        .focal_max(1)
        .focal_min(1)
        .focal_mode(2)
    )

    water = water.updateMask(
        water.connectedPixelCount(
            300,
            True
        ).gte(300)
    )

    water = water.clip(
        offshore_zone.buffer(1000)
    )

    edge = ee.Algorithms.CannyEdgeDetector(
        image=water,
        threshold=0.1,
        sigma=2
    )

    edge = (
        edge
        .focal_max(1)
        .focal_mode(1)
        .selfMask()
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
                scale=120,
                bestEffort=True,
                tileScale=8,
                maxPixels=1e8
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
        "water": water.rename("water"),
        "edge": edge.rename("shoreline"),
        "vals": vals
    }

# =========================
# CALCULATE AREA - SAFE
# =========================
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

        aoi, search_zone = get_region_and_zone(
            province
        )

        r1 = get_analysis(
            search_zone,
            aoi,
            y1,
            include_heavy=False
        )

        r2 = get_analysis(
            search_zone,
            aoi,
            y2,
            include_heavy=False
        )

        erosion = (
            r1["water"]
            .And(
                r2["water"].Not()
            )
            .rename("erosion")
            .selfMask()
        )

        accretion = (
            r2["water"]
            .And(
                r1["water"].Not()
            )
            .rename("accretion")
            .selfMask()
        )

        erosion_ha = calculate_area(
            erosion,
            "erosion",
            search_zone
        )

        accretion_ha = calculate_area(
            accretion,
            "accretion",
            search_zone
        )

        save_data(
            province,
            int(y2),
            float(r2["vals"].get("NDWI", 0) or 0),
            float(r2["vals"].get("MNDWI", 0) or 0),
            erosion_ha,
            accretion_ha
        )

        bounds = safe_bounds(search_zone)

        result = {

            "mode": "true-coast",

            "message": "Đã tải đúng dải ven biển: NDWI/MNDWI chỉ hiển thị quanh tiếp xúc đất - biển, không lấy biên trong đất liền.",

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
                        width=2
                    ),
                    {
                        "palette": ["yellow"]
                    }
                ),

                "ndwi1":
                get_map_url(
                    r1["ndwi"],
                    {
                        "min": -0.5,
                        "max": 0.5,
                        "palette": [
                            "brown",
                            "yellow",
                            "green",
                            "cyan",
                            "blue"
                        ]
                    }
                ),

                "ndwi2":
                get_map_url(
                    r2["ndwi"],
                    {
                        "min": -0.5,
                        "max": 0.5,
                        "palette": [
                            "brown",
                            "yellow",
                            "green",
                            "cyan",
                            "blue"
                        ]
                    }
                ),

                "mndwi1":
                get_map_url(
                    r1["mndwi"],
                    {
                        "min": -0.5,
                        "max": 0.5,
                        "palette": [
                            "purple",
                            "black",
                            "white",
                            "cyan",
                            "blue"
                        ]
                    }
                ),

                "mndwi2":
                get_map_url(
                    r2["mndwi"],
                    {
                        "min": -0.5,
                        "max": 0.5,
                        "palette": [
                            "purple",
                            "black",
                            "white",
                            "cyan",
                            "blue"
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

        cache_key = f"{province}_{y1}_{y2}_{layer}_true_coast"

        if cache_key in tile_cache:

            return jsonify({
                "mode": "advanced-cache",
                "layer": layer,
                "layers": {
                    layer: tile_cache[cache_key]
                }
            })

        aoi, search_zone = get_region_and_zone(
            province
        )

        if layer == "shoreline1":

            r1 = get_analysis(
                search_zone,
                aoi,
                y1,
                include_heavy=True
            )

            url = get_map_url(
                r1["edge"],
                {
                    "palette": ["#ff00ff"]
                }
            )

        elif layer == "shoreline2":

            r2 = get_analysis(
                search_zone,
                aoi,
                y2,
                include_heavy=True
            )

            url = get_map_url(
                r2["edge"],
                {
                    "palette": ["#00ffff"]
                }
            )

        elif layer in ["erosion", "accretion"]:

            r1 = get_analysis(
                search_zone,
                aoi,
                y1,
                include_heavy=True
            )

            r2 = get_analysis(
                search_zone,
                aoi,
                y2,
                include_heavy=True
            )

            erosion = (
                r1["water"]
                .And(
                    r2["water"].Not()
                )
                .rename("erosion")
                .selfMask()
            )

            accretion = (
                r2["water"]
                .And(
                    r1["water"].Not()
                )
                .rename("accretion")
                .selfMask()
            )

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
# CHAT AI GIS
# =========================
@app.route("/chat_ai", methods=["POST"])
def chat_ai():

    try:

        if not client:

            return jsonify({
                "error": "Thiếu GEMINI_API_KEY trong Render Environment"
            }), 500

        data = request.get_json()

        if not data:

            return jsonify({
                "error": "Không có dữ liệu gửi lên"
            }), 400

        prompt = f"""
Tỉnh: {data.get('province')}
Dữ liệu: {data.get('stats')}
Câu hỏi: {data.get('question')}

Hãy trả lời bằng tiếng Việt, ngắn gọn, dễ hiểu, có nhận xét về xói mòn, bồi tụ, NDWI và MNDWI.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        answer = getattr(response, "text", None)

        if not answer:

            return jsonify({
                "error": "AI không phản hồi"
            }), 500

        return jsonify({
            "answer": answer
        })

    except Exception as e:

        print(traceback.format_exc())

        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        }), 500


# =========================
# RUN LOCAL
# =========================
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )