import os
import json
import sqlite3
import traceback

import ee
import numpy as np
import pandas as pd

from flask import Flask, request, jsonify
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
# HOME ROUTE
# =========================
@app.route("/")
def home():
    return jsonify({
        "status": "WebGIS API is running",
        "gee_test": "/gee?province=Da%20Nang&y1=2020&y2=2024",
        "forecast_test": "/forecast?province=Da%20Nang",
        "chat_ai": "/chat_ai"
    })


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


def init_gee():

    global gee_ready
    global provinces_fc
    global gsw
    global permanent_water

    if gee_ready:
        return

    service_account = "gee-coastline@cach-471019.iam.gserviceaccount.com"

    if os.environ.get("GOOGLE_CREDS_JSON"):

        info = json.loads(
            os.environ["GOOGLE_CREDS_JSON"]
        )

        with open("service_account.json", "w") as f:
            json.dump(info, f)

    if not os.path.exists("service_account.json"):
        raise FileNotFoundError(
            "Không tìm thấy service_account.json hoặc GOOGLE_CREDS_JSON trên Render"
        )

    credentials = ee.ServiceAccountCredentials(
        service_account,
        "service_account.json"
    )

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
def get_analysis(offshore_zone, year):

    dataset = (
        ee.ImageCollection(
            "LANDSAT/LC08/C02/T1_L2"
        )
        .filterBounds(offshore_zone)
        .filterDate(
            f"{year}-01-01",
            f"{year}-12-31"
        )
        .filter(
            ee.Filter.lt(
                "CLOUD_COVER",
                60
            )
        )
        .sort("CLOUD_COVER")
        .map(mask_l8_sr)
        .limit(10)
    )

    count = dataset.size().getInfo()

    if count == 0:
        raise Exception(
            f"Không có ảnh Landsat cho năm {year}. Hãy thử năm khác."
        )

    img = (
        dataset
        .first()
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

    water = mndwi.gt(0.12)

    water = water.And(
        permanent_water
    )

    water = (
        water
        .focal_max(1)
        .focal_min(1)
    )

    water = water.updateMask(
        water.connectedPixelCount(
            30,
            True
        ).gte(30)
    )

    edge = (
        ee.Algorithms.CannyEdgeDetector(
            image=water,
            threshold=0.1,
            sigma=1
        )
        .selfMask()
    )

    try:

        stats = (
            ndwi.addBands(mndwi)
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=offshore_zone,
                scale=500,
                bestEffort=True,
                tileScale=16,
                maxPixels=1e8
            )
            .getInfo()
        )

    except Exception as e:

        print("STATS ERROR:", e)

        stats = {
            "NDWI": 0,
            "MNDWI": 0
        }

    if not stats:

        stats = {
            "NDWI": 0,
            "MNDWI": 0
        }

    return {
        "ndwi": ndwi,
        "mndwi": mndwi,
        "water": water.rename("water"),
        "edge": edge,
        "vals": stats
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
# API GEE
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

        if province in non_coastal:

            return jsonify({
                "error": f"Tỉnh {province} không giáp biển"
            }), 400

        selected = next(
            (
                d for d in coastal_data
                if d["label"] == province
            ),
            None
        )

        if not selected:

            return jsonify({
                "error": f"Không tìm thấy tỉnh {province}"
            }), 404

        region = provinces_fc.filter(
            ee.Filter.inList(
                "ADM1_NAME",
                selected["search"]
            )
        )

        try:

            count_region = region.size().getInfo()

        except Exception as e:

            print("REGION ERROR:", e)

            return jsonify({
                "error": "Không đọc được ranh giới tỉnh từ Google Earth Engine",
                "type": type(e).__name__
            }), 500

        if count_region == 0:

            return jsonify({
                "error": f"Không tìm thấy ranh giới GEE cho {province}"
            }), 404

        aoi = (
            region
            .geometry()
            .dissolve()
        )

        coastal_buffer = aoi.buffer(1000)

        offshore_zone = coastal_buffer.difference(
            aoi,
            1
        )

        offshore_zone = offshore_zone.intersection(
            aoi.bounds(),
            1
        )

        r1 = get_analysis(
            offshore_zone,
            y1
        )

        r2 = get_analysis(
            offshore_zone,
            y2
        )

        erosion = (
            r1["water"]
            .And(
                r2["water"].Not()
            )
            .rename("erosion")
            .updateMask(
                r1["water"].And(
                    r2["water"].Not()
                )
            )
        )

        accretion = (
            r2["water"]
            .And(
                r1["water"].Not()
            )
            .rename("accretion")
            .updateMask(
                r2["water"].And(
                    r1["water"].Not()
                )
            )
        )

        # Render free bị timeout khi tính diện tích bằng reduceRegion/getInfo.
        # Tạm thời set 0 để /gee trả layer bản đồ nhanh, không bị Internal Server Error.
        erosion_ha = 0

        accretion_ha = 0

        save_data(
            province,
            int(y1),
            float(r1["vals"].get("NDWI", 0) or 0),
            float(r1["vals"].get("MNDWI", 0) or 0),
            erosion_ha,
            accretion_ha
        )

        try:

            bounds = aoi.bounds().getInfo()["coordinates"][0]

        except Exception as e:

            print("BOUNDS ERROR:", e)

            bounds = [
                [108.0, 16.0],
                [109.0, 16.0],
                [109.0, 17.0],
                [108.0, 17.0],
                [108.0, 16.0]
            ]

        result = {

            "layers": {

                "boundary":
                ee.Image()
                .byte()
                .paint(
                    featureCollection=ee.FeatureCollection([
                        ee.Feature(aoi)
                    ]),
                    color=1,
                    width=3
                )
                .getMapId({
                    "palette": ["yellow"]
                })["tile_fetcher"].url_format,

                "shoreline1":
                r1["edge"]
                .getMapId({
                    "palette": ["#ff00ff"]
                })["tile_fetcher"].url_format,

                "shoreline2":
                r2["edge"]
                .getMapId({
                    "palette": ["#00ffff"]
                })["tile_fetcher"].url_format,

                "erosion":
                erosion
                .getMapId({
                    "palette": ["red"]
                })["tile_fetcher"].url_format,

                "accretion":
                accretion
                .getMapId({
                    "palette": ["lime"]
                })["tile_fetcher"].url_format,

                "ndwi1":
                r1["ndwi"]
                .getMapId({
                    "min": -1,
                    "max": 1,
                    "palette": [
                        "white",
                        "blue"
                    ]
                })["tile_fetcher"].url_format,

                "ndwi2":
                r2["ndwi"]
                .getMapId({
                    "min": -1,
                    "max": 1,
                    "palette": [
                        "white",
                        "blue"
                    ]
                })["tile_fetcher"].url_format,

                "mndwi1":
                r1["mndwi"]
                .getMapId({
                    "min": -1,
                    "max": 1,
                    "palette": [
                        "white",
                        "green"
                    ]
                })["tile_fetcher"].url_format,

                "mndwi2":
                r2["mndwi"]
                .getMapId({
                    "min": -1,
                    "max": 1,
                    "palette": [
                        "white",
                        "green"
                    ]
                })["tile_fetcher"].url_format
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