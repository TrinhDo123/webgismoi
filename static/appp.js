const BASE_URL = "https://webgismoi.onrender.com";
const API_URL = `${BASE_URL}/gee`;

// Chỉ giữ các tỉnh/vùng có bờ biển thật.
// Không cho chọn tỉnh nội địa như An Giang, Bắc Ninh, Điện Biên...
const provinces = [
    "Ca Mau",
    "Ha Tinh",
    "Khanh Hoa",
    "Nghe An",
    "Quang Ngai",
    "Quang Ninh",
    "Quang Tri",
    "Thanh Hoa",
    "Da Nang",
    "Hai Phong",
    "TP Ho Chi Minh",
    "Hue",
    "Vinh Long"
];

const provinceSelect = document.getElementById("province");
const y1Select = document.getElementById("y1");
const y2Select = document.getElementById("y2");

provinces.forEach(p => {
    provinceSelect.add(
        new Option(p, p)
    );
});

for (let y = 2015; y <= 2026; y++) {
    y1Select.add(
        new Option(y, y)
    );

    y2Select.add(
        new Option(y, y)
    );
}

provinceSelect.value = "Khanh Hoa";
y1Select.value = 2020;
y2Select.value = 2024;

const map = L.map("map").setView([12.3, 109.1], 8);

L.tileLayer(
    "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    {
        attribution: "Google Satellite"
    }
).addTo(map);

let layers = {};
let resData = null;
let chart1 = null;
let chart2 = null;

const heavyLayers = [
    "shoreline1",
    "shoreline2",
    "erosion",
    "accretion"
];

// Đọc JSON an toàn để tránh lỗi: Unexpected token '<', '<html>...'
async function fetchJSON(url, options = {}) {
    const response = await fetch(url, options);
    const text = await response.text();

    let data;

    try {
        data = JSON.parse(text);
    } catch (e) {
        throw new Error(
            "Server không trả về JSON. Có thể API bị lỗi hoặc timeout. HTTP " +
            response.status +
            ". Nội dung đầu: " +
            text.slice(0, 160)
        );
    }

    if (!response.ok) {
        throw new Error(
            data.error || `HTTP ${response.status}`
        );
    }

    return data;
}

function clearMapLayers() {
    Object.values(layers).forEach(layer => {
        if (map.hasLayer(layer)) {
            map.removeLayer(layer);
        }
    });

    layers = {};
}

function buildLayerUI() {
    const y1 = y1Select.value;
    const y2 = y2Select.value;

    const config = [
        { id: "boundary", name: "Ranh giới vùng bờ" },
        { id: "coast_strip", name: "Dải ven biển thật" },
        { id: "shoreline1", name: "Đường bờ " + y1 },
        { id: "shoreline2", name: "Đường bờ " + y2 },
        { id: "erosion", name: "Xói mòn" },
        { id: "accretion", name: "Bồi tụ" },
        { id: "ndwi1", name: "NDWI " + y1 },
        { id: "ndwi2", name: "NDWI " + y2 },
        { id: "mndwi1", name: "MNDWI " + y1 },
        { id: "mndwi2", name: "MNDWI " + y2 }
    ];

    const list = document.getElementById("layer-list");

    list.innerHTML = "";

    config.forEach(l => {
        list.innerHTML += `
            <div class="layer-item">
                <span>${l.name}</span>
                <input
                    type="checkbox"
                    id="chk_${l.id}"
                    onchange="toggleLayer('${l.id}')"
                >
            </div>
        `;
    });
}

async function toggleLayer(id) {
    const chk = document.getElementById("chk_" + id);

    if (!chk) return;

    const checked = chk.checked;

    if (!checked) {
        if (layers[id] && map.hasLayer(layers[id])) {
            map.removeLayer(layers[id]);
        }

        return;
    }

    if (layers[id]) {
        layers[id].addTo(map);
        return;
    }

    if (heavyLayers.includes(id)) {
        await loadHeavyLayer(id);
        return;
    }

    alert("Lớp này chưa có dữ liệu. Hãy chạy phân tích trước.");
    chk.checked = false;
}

async function loadHeavyLayer(layerId) {
    try {
        const chk = document.getElementById("chk_" + layerId);

        if (chk) {
            chk.disabled = true;
        }

        const province = encodeURIComponent(
            provinceSelect.value
        );

        const y1 = y1Select.value;
        const y2 = y2Select.value;

        const heavyUrl =
            `${BASE_URL}/gee_heavy?province=${province}&y1=${y1}&y2=${y2}&layer=${layerId}`;

        console.log("HEAVY LAYER URL:", heavyUrl);

        const data = await fetchJSON(heavyUrl);

        if (!data.layers || !data.layers[layerId]) {
            throw new Error(
                "Server không trả về dữ liệu layer " + layerId
            );
        }

        layers[layerId] = L.tileLayer(
            data.layers[layerId],
            {
                opacity: 0.9
            }
        );

        layers[layerId].addTo(map);

        if (chk) {
            chk.checked = true;
            chk.disabled = false;
        }

    } catch (err) {
        console.log(err);

        const chk = document.getElementById("chk_" + layerId);

        if (chk) {
            chk.checked = false;
            chk.disabled = false;
        }

        alert(err.message || "Lỗi tải lớp nâng cao");
    }
}

async function startAnalysis() {
    const btn = document.getElementById("btnStart");

    btn.innerHTML = "⌛ ĐANG XỬ LÝ...";
    btn.disabled = true;

    buildLayerUI();
    clearMapLayers();

    try {
        const province = encodeURIComponent(
            provinceSelect.value
        );

        const y1 = y1Select.value;
        const y2 = y2Select.value;

        const url = `${API_URL}?province=${province}&y1=${y1}&y2=${y2}`;

        console.log("API URL:", url);

        const data = await fetchJSON(url);

        resData = data;

        for (let k in resData.layers) {
            layers[k] = L.tileLayer(
                resData.layers[k],
                {
                    opacity: 0.85
                }
            );

            // Chỉ bật mặc định các lớp nhẹ để không làm rối bản đồ.
            if (
                [
                    "boundary",
                    "shoreline1",
                    "shoreline2"
                ].includes(k)
            ) {
                layers[k].addTo(map);

                const chk = document.getElementById("chk_" + k);

                if (chk) {
                    chk.checked = true;
                }
            }
        }

        const b = resData.bounds;

        if (Array.isArray(b) && b.length > 0) {
            const bounds = L.latLngBounds(
                b.map(p => [p[1], p[0]])
            );

            map.fitBounds(bounds);
        }

        updateStats();
        renderCharts();
        loadForecast();

    } catch (err) {
        console.log(err);
        alert(err.message);
    }

    btn.innerHTML = "🚀 CHẠY PHÂN TÍCH";
    btn.disabled = false;
}

function updateStats() {
    if (!resData) return;

    const s = resData.stats;

    document.getElementById("stats-info").innerHTML = `
        <div class="info-box">
            <b>Năm ${y1Select.value}</b>
            <br><br>
            NDWI:
            <span class="success">
                ${Number(s.year1.NDWI).toFixed(4)}
            </span>
            <br>
            MNDWI:
            <span class="success">
                ${Number(s.year1.MNDWI).toFixed(4)}
            </span>
        </div>

        <div class="info-box">
            <b>Năm ${y2Select.value}</b>
            <br><br>
            NDWI:
            <span class="success">
                ${Number(s.year2.NDWI).toFixed(4)}
            </span>
            <br>
            MNDWI:
            <span class="success">
                ${Number(s.year2.MNDWI).toFixed(4)}
            </span>
        </div>

        <div class="info-box">
            🔴 Xói mòn:
            <span class="danger">
                ${Number(s.erosion_ha).toFixed(2)} ha
            </span>
            <br><br>
            🟢 Bồi tụ:
            <span class="success">
                ${Number(s.accretion_ha).toFixed(2)} ha
            </span>
        </div>
    `;
}

async function loadForecast() {
    try {
        const province = encodeURIComponent(
            provinceSelect.value
        );

        const data = await fetchJSON(
            `${BASE_URL}/forecast?province=${province}`
        );

        if (data.error) {
            document.getElementById("ai-report").innerHTML = `
                <span style="color:red">
                    ${data.error}
                </span>
            `;
            return;
        }

        if (!Array.isArray(data) || data.length === 0) {
            document.getElementById("ai-report").innerHTML = `
                <span style="color:red">
                    Chưa có dữ liệu dự báo
                </span>
            `;
            return;
        }

        const s = resData.stats;

        const erosion = Number(s.erosion_ha || 0);
        const accretion = Number(s.accretion_ha || 0);

        const ndwi = (
            Number(s.year1.NDWI || 0) +
            Number(s.year2.NDWI || 0)
        ) / 2;

        const mndwi = (
            Number(s.year1.MNDWI || 0) +
            Number(s.year2.MNDWI || 0)
        ) / 2;

        let erosionText = "";
        let ndwiText = "";
        let mndwiText = "";

        if (erosion > accretion) {
            erosionText = `
                Khu vực đang có xu hướng
                <b style="color:red">xói mòn mạnh hơn bồi tụ</b>.
            `;
        } else if (accretion > erosion) {
            erosionText = `
                Khu vực có xu hướng
                <b style="color:green">bồi tụ mạnh hơn xói mòn</b>.
            `;
        } else {
            erosionText = `
                Khu vực đang tương đối cân bằng giữa xói mòn và bồi tụ.
            `;
        }

        if (ndwi < -0.3) {
            ndwiText = "NDWI thấp, khu vực có tín hiệu nước bề mặt yếu.";
        } else if (ndwi <= 0.3) {
            ndwiText = "NDWI trung bình, phản ánh vùng chuyển tiếp đất - nước.";
        } else {
            ndwiText = "NDWI cao, khu vực có tín hiệu nước mặt rõ.";
        }

        if (mndwi < -0.3) {
            mndwiText = "MNDWI thấp, khả năng nhận diện nước yếu.";
        } else if (mndwi <= 0.3) {
            mndwiText = "MNDWI trung bình, phù hợp vùng ven biển/đất ngập nước.";
        } else {
            mndwiText = "MNDWI cao, thể hiện vùng nước mặt rõ rệt.";
        }

        const lastPred = data[data.length - 1].prediction;

        let html = `
        <div style="line-height:1.9;text-align:justify;font-size:13px;">
            <b style="font-size:15px;color:#1e293b;">
                🧠 PHÂN TÍCH AI VEN BIỂN
            </b>
            <br><br>
            Khu vực nghiên cứu: <b>${provinceSelect.value}</b>
            <br><br>
            ${erosionText}
            <br><br>
            ${ndwiText}
            <br><br>
            ${mndwiText}
            <br><br>
            AI dự báo đến năm <b>${data[data.length - 1].year}</b> mức biến động có thể đạt:
            <br><br>
            <div style="background:#fee2e2;padding:12px;border-radius:10px;color:#b91c1c;font-weight:bold;text-align:center;font-size:18px;">
                ${Number(lastPred).toFixed(2)} ha
            </div>
            <br>
            <b>Khuyến nghị:</b>
            <ul>
                <li>Giám sát ảnh vệ tinh định kỳ</li>
                <li>Phục hồi rừng ngập mặn</li>
                <li>Ứng dụng AI cảnh báo sớm</li>
                <li>Quản lý khai thác ven biển</li>
            </ul>
            <b>🔮 Dự báo chi tiết:</b>
            <br><br>
        `;

        data.forEach(item => {
            html += `
                📅 Năm ${item.year}:
                <b style="color:red">
                    ${Number(item.prediction).toFixed(2)} ha
                </b>
                <br><br>
            `;
        });

        html += `</div>`;

        document.getElementById("ai-report").innerHTML = html;

    } catch (err) {
        console.log(err);

        document.getElementById("ai-report").innerHTML = `
            <span style="color:red">
                Lỗi tải dự báo AI hoặc chưa đủ dữ liệu
            </span>
        `;
    }
}

async function askAI() {
    const question = document.getElementById("ai-question").value;

    if (!question) {
        alert("Nhập câu hỏi");
        return;
    }

    if (!resData) {
        alert("Hãy chạy phân tích trước");
        return;
    }

    const answerBox = document.getElementById("ai-answer");

    answerBox.innerHTML = "⌛ AI đang phân tích dữ liệu viễn thám...";

    try {
        const data = await fetchJSON(
            `${BASE_URL}/chat_ai`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    question: question,
                    province: provinceSelect.value,
                    stats: resData.stats
                })
            }
        );

        if (!data.answer) {
            throw new Error("AI không trả về kết quả");
        }

        answerBox.innerText = data.answer;

    } catch (err) {
        console.log(err);

        answerBox.innerHTML = `
            <span style="color:red">
                ${err.message || "Lỗi kết nối AI"}
            </span>
        `;
    }
}

function renderCharts() {
    if (!resData) return;

    if (chart1) chart1.destroy();
    if (chart2) chart2.destroy();

    const s = resData.stats;

    const year1 = y1Select.value;
    const year2 = y2Select.value;

    chart1 = new Chart(
        document.getElementById("chart1"),
        {
            type: "bar",
            data: {
                labels: [
                    "NDWI " + year1,
                    "MNDWI " + year1,
                    "NDWI " + year2,
                    "MNDWI " + year2
                ],
                datasets: [{
                    label: "Giá trị",
                    data: [
                        Number(s.year1.NDWI),
                        Number(s.year1.MNDWI),
                        Number(s.year2.NDWI),
                        Number(s.year2.MNDWI)
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        }
    );

    chart2 = new Chart(
        document.getElementById("chart2"),
        {
            type: "pie",
            data: {
                labels: [
                    "Xói mòn",
                    "Bồi tụ"
                ],
                datasets: [{
                    data: [
                        Number(s.erosion_ha),
                        Number(s.accretion_ha)
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        }
    );
}

buildLayerUI();