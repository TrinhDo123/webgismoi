const BASE_URL = window.location.origin.includes("localhost") || window.location.origin.includes("127.0.0.1")
    ? "http://127.0.0.1:5000"
    : window.location.origin;

const API_URL = `${BASE_URL}/gee`;

const provinces = [
    "An Giang",
    "Bac Ninh",
    "Ca Mau",
    "Cao Bang",
    "Dak Lak",
    "Dien Bien",
    "Dong Nai",
    "Dong Thap",
    "Gia Lai",
    "Ha Tinh",
    "Hung Yen",
    "Khanh Hoa",
    "Lai Chau",
    "Lam Dong",
    "Lang Son",
    "Lao Cai",
    "Nghe An",
    "Ninh Binh",
    "Phu Tho",
    "Quang Ngai",
    "Quang Ninh",
    "Quang Tri",
    "Son La",
    "Tay Ninh",
    "Thai Nguyen",
    "Thanh Hoa",
    "Can Tho",
    "Da Nang",
    "Ha Noi",
    "Hai Phong",
    "TP Ho Chi Minh",
    "Hue",
    "Tuyen Quang",
    "Vinh Long"
];

const provinceSelect = document.getElementById("province");
const y1Select = document.getElementById("y1");
const y2Select = document.getElementById("y2");

provinces.forEach(p => provinceSelect.add(new Option(p, p)));

for (let y = 2015; y <= 2026; y++) {
    y1Select.add(new Option(y, y));
    y2Select.add(new Option(y, y));
}

provinceSelect.value = "An Giang";
y1Select.value = 2016;
y2Select.value = 2024;

const map = L.map("map").setView([10.2, 105.4], 7);

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

function getLayerLabel(id) {
    const y1 = y1Select.value;
    const y2 = y2Select.value;

    const labels = {
        boundary: "Ranh giới",
        shoreline1: "Đường bờ " + y1,
        shoreline2: "Đường bờ " + y2,
        erosion: "Xói mòn",
        accretion: "Bồi tụ",
        ndwi1: "NDWI " + y1,
        ndwi2: "NDWI " + y2,
        mndwi1: "MNDWI " + y1,
        mndwi2: "MNDWI " + y2
    };

    return labels[id] || id;
}

function buildLayerUI() {
    const config = [
        { id: "boundary", name: getLayerLabel("boundary") },
        { id: "shoreline1", name: getLayerLabel("shoreline1") },
        { id: "shoreline2", name: getLayerLabel("shoreline2") },
        { id: "erosion", name: getLayerLabel("erosion") },
        { id: "accretion", name: getLayerLabel("accretion") },
        { id: "ndwi1", name: getLayerLabel("ndwi1") },
        { id: "ndwi2", name: getLayerLabel("ndwi2") },
        { id: "mndwi1", name: getLayerLabel("mndwi1") },
        { id: "mndwi2", name: getLayerLabel("mndwi2") }
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

async function fetchJSON(url, options = {}) {
    const response = await fetch(url, options);
    const text = await response.text();

    let data;

    try {
        data = JSON.parse(text);
    } catch (e) {
        throw new Error(
            "Server không trả về JSON. HTTP " +
            response.status +
            ". Nội dung đầu: " +
            text.slice(0, 180)
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

async function toggleLayer(id) {
    const chk = document.getElementById("chk_" + id);

    if (!chk) return;

    if (!chk.checked) {
        if (layers[id] && map.hasLayer(layers[id])) {
            map.removeLayer(layers[id]);
        }
        return;
    }

    if (layers[id]) {
        layers[id].addTo(map);
        return;
    }

    if (!resData) {
        chk.checked = false;
        alert("Hãy bấm CHẠY PHÂN TÍCH trước.");
        return;
    }

    if (heavyLayers.includes(id)) {
        await loadHeavyLayer(id);
        return;
    }

    chk.checked = false;
    alert("Lớp này chưa có dữ liệu từ API.");
}

async function loadHeavyLayer(layerId) {
    const chk = document.getElementById("chk_" + layerId);

    try {
        if (chk) {
            chk.disabled = true;
        }

        const province = encodeURIComponent(provinceSelect.value);
        const y1 = y1Select.value;
        const y2 = y2Select.value;

        const url = `${BASE_URL}/gee_heavy?province=${province}&y1=${y1}&y2=${y2}&layer=${layerId}`;

        console.log("HEAVY API URL:", url);

        const data = await fetchJSON(url);

        if (!data.layers || !data.layers[layerId]) {
            throw new Error("Server không trả về dữ liệu cho lớp " + getLayerLabel(layerId));
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
        }

    } catch (err) {
        console.log(err);

        if (chk) {
            chk.checked = false;
        }

        alert(err.message || "Lỗi tải lớp nâng cao");

    } finally {
        if (chk) {
            chk.disabled = false;
        }
    }
}

async function startAnalysis() {
    const btn = document.getElementById("btnStart");

    btn.innerHTML = "⌛ ĐANG XỬ LÝ...";
    btn.disabled = true;

    buildLayerUI();
    clearMapLayers();

    try {
        const province = encodeURIComponent(provinceSelect.value);
        const y1 = y1Select.value;
        const y2 = y2Select.value;
        const url = `${API_URL}?province=${province}&y1=${y1}&y2=${y2}`;

        console.log("API URL:", url);

        const data = await fetchJSON(url);
        resData = data;

        if (!resData.layers) {
            throw new Error("API không trả về layers.");
        }

        for (let k in resData.layers) {
            layers[k] = L.tileLayer(
                resData.layers[k],
                {
                    opacity: 0.85
                }
            );

            // Route /gee chỉ cần bật sẵn ranh giới.
            // Đường bờ / xói mòn / bồi tụ sẽ tải bằng /gee_heavy khi tick checkbox.
            if (["boundary"].includes(k)) {
                layers[k].addTo(map);
                const chk = document.getElementById("chk_" + k);
                if (chk) chk.checked = true;
            }
        }

        const b = resData.bounds;
        if (Array.isArray(b) && b.length > 2) {
            try {
                const bounds = L.latLngBounds(
                    b.map(p => [p[1], p[0]])
                );
                map.fitBounds(bounds);
            } catch (e) {
                map.fitBounds([
                    [b[0][1], b[0][0]],
                    [b[2][1], b[2][0]]
                ]);
            }
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
    if (!resData || !resData.stats) return;

    const s = resData.stats;

    document.getElementById("stats-info").innerHTML = `
        <div class="info-box">
            <b>Năm ${y1Select.value}</b>
            <br><br>
            NDWI:
            <span class="success">${Number(s.year1.NDWI || 0).toFixed(4)}</span>
            <br>
            MNDWI:
            <span class="success">${Number(s.year1.MNDWI || 0).toFixed(4)}</span>
        </div>

        <div class="info-box">
            <b>Năm ${y2Select.value}</b>
            <br><br>
            NDWI:
            <span class="success">${Number(s.year2.NDWI || 0).toFixed(4)}</span>
            <br>
            MNDWI:
            <span class="success">${Number(s.year2.MNDWI || 0).toFixed(4)}</span>
        </div>

        <div class="info-box">
            🔴 Xói mòn:
            <span class="danger">${Number(s.erosion_ha || 0).toFixed(2)} ha</span>
            <br><br>
            🟢 Bồi tụ:
            <span class="success">${Number(s.accretion_ha || 0).toFixed(2)} ha</span>
        </div>
    `;
}

async function loadForecast() {
    try {
        const province = encodeURIComponent(provinceSelect.value);
        const data = await fetchJSON(`${BASE_URL}/forecast?province=${province}`);

        if (data.error || !Array.isArray(data) || data.length === 0) {
            document.getElementById("ai-report").innerHTML = `
                <span style="color:red">${data.error || "Chưa có dữ liệu dự báo"}</span>
            `;
            return;
        }

        const s = resData.stats;
        const erosion = Number(s.erosion_ha || 0);
        const accretion = Number(s.accretion_ha || 0);
        const ndwi = (Number(s.year1.NDWI || 0) + Number(s.year2.NDWI || 0)) / 2;
        const mndwi = (Number(s.year1.MNDWI || 0) + Number(s.year2.MNDWI || 0)) / 2;

        let erosionText = "";
        let ndwiText = "";
        let mndwiText = "";

        if (erosion > accretion) {
            erosionText = `
                Khu vực đang có xu hướng
                <b style="color:red">xói mòn mạnh hơn bồi tụ</b>.
                Điều này cho thấy đường bờ biển có nguy cơ bị thu hẹp theo thời gian,
                đặc biệt dưới tác động của sóng biển, dòng chảy và biến đổi khí hậu.
            `;
        } else if (accretion > erosion) {
            erosionText = `
                Khu vực có xu hướng
                <b style="color:green">bồi tụ mạnh hơn xói mòn</b>.
                Điều này phản ánh quá trình tích tụ trầm tích đang diễn ra tương đối tốt.
            `;
        } else {
            erosionText = `
                Khu vực đang ở trạng thái tương đối cân bằng giữa xói mòn và bồi tụ.
            `;
        }

        if (ndwi < -0.3) {
            ndwiText = "Chỉ số NDWI ở mức thấp, phản ánh khu vực có lượng nước bề mặt ít.";
        } else if (ndwi <= 0.3) {
            ndwiText = "Chỉ số NDWI ở mức trung bình, phản ánh trạng thái chuyển tiếp giữa đất và nước hoặc khu vực ẩm ướt.";
        } else {
            ndwiText = "Chỉ số NDWI cao, cho thấy sự hiện diện mạnh của nước bề mặt.";
        }

        if (mndwi < -0.3) {
            mndwiText = "Chỉ số MNDWI thấp, phản ánh khu vực có khả năng chứa nước thấp.";
        } else if (mndwi <= 0.3) {
            mndwiText = "Chỉ số MNDWI ở mức trung bình, cho thấy khu vực có sự pha trộn giữa nước và đất ngập ẩm.";
        } else {
            mndwiText = "Chỉ số MNDWI cao, phản ánh khả năng tồn tại nước mặt rõ rệt.";
        }

        const last = data[data.length - 1];

        let html = `
        <div style="line-height:1.9;text-align:justify;font-size:13px;">
            <b style="font-size:15px;color:#1e293b;">🧠 PHÂN TÍCH AI VEN BIỂN</b>
            <br><br>
            Khu vực nghiên cứu: <b>${provinceSelect.value}</b>
            <br><br>
            ${erosionText}
            <br><br>
            ${ndwiText}
            <br><br>
            ${mndwiText}
            <br><br>
            AI dự báo rằng đến năm <b>${last.year}</b> mức biến động có thể đạt:
            <br><br>
            <div style="background:#fee2e2;padding:12px;border-radius:10px;color:#b91c1c;font-weight:bold;text-align:center;font-size:18px;">
                ${Number(last.prediction).toFixed(2)} ha
            </div>
            <br>
            <b>Khuyến nghị:</b>
            <ul>
                <li>Giám sát ảnh vệ tinh định kỳ</li>
                <li>Phục hồi rừng ngập mặn</li>
                <li>Ứng dụng AI cảnh báo sớm</li>
                <li>Quản lý khai thác ven biển</li>
                <li>Theo dõi biến động thủy văn</li>
            </ul>
            <b>🔮 Dự báo chi tiết:</b>
            <br><br>
        `;

        data.forEach(item => {
            html += `
                📅 Năm ${item.year}:
                <b style="color:red">${Number(item.prediction).toFixed(2)} ha</b>
                <br><br>
            `;
        });

        html += `</div>`;
        document.getElementById("ai-report").innerHTML = html;

    } catch (err) {
        console.log(err);
        document.getElementById("ai-report").innerHTML = `
            <span style="color:red">Lỗi tải dự báo AI hoặc chưa đủ dữ liệu</span>
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
            <span style="color:red">${err.message || "Lỗi kết nối AI"}</span>
        `;
    }
}

function renderCharts() {
    if (!resData || !resData.stats) return;

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
                        Number(s.year1.NDWI || 0),
                        Number(s.year1.MNDWI || 0),
                        Number(s.year2.NDWI || 0),
                        Number(s.year2.MNDWI || 0)
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
                        Number(s.erosion_ha || 0),
                        Number(s.accretion_ha || 0)
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
