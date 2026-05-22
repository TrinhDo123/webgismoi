const BASE_URL = "https://webgismoi.onrender.com";

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

y1Select.value = 2020;
y2Select.value = 2024;

const map = L.map("map").setView([16, 108], 6);

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

function buildLayerUI() {

    const y1 = y1Select.value;
    const y2 = y2Select.value;

    const config = [
        { id: "boundary", name: "Ranh giới" },
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

function toggleLayer(id) {

    if (!layers[id]) return;

    const checked = document.getElementById(
        "chk_" + id
    ).checked;

    if (checked) {
        layers[id].addTo(map);
    } else {
        map.removeLayer(layers[id]);
    }
}

async function startAnalysis() {

    const btn = document.getElementById("btnStart");

    btn.innerHTML = "⌛ ĐANG XỬ LÝ...";
    btn.disabled = true;

    buildLayerUI();

    try {

        const province = encodeURIComponent(
            provinceSelect.value
        );

        const y1 = y1Select.value;
        const y2 = y2Select.value;

        const url =
            `${API_URL}?province=${province}&y1=${y1}&y2=${y2}`;

        console.log(url);

        const response = await fetch(url);

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Flask lỗi"
            );
        }

        resData = data;

        Object.values(layers).forEach(layer => {
            if (map.hasLayer(layer)) {
                map.removeLayer(layer);
            }
        });

        layers = {};

        for (let k in resData.layers) {

            layers[k] = L.tileLayer(
                resData.layers[k],
                {
                    opacity: 0.8
                }
            );

            if (
                [
                    "boundary",
                    "erosion",
                    "accretion"
                ].includes(k)
            ) {
                layers[k].addTo(map);

                document.getElementById(
                    "chk_" + k
                ).checked = true;
            }
        }

        const b = resData.bounds;

        const bounds = L.latLngBounds(
            b.map(p => [p[1], p[0]])
        );

        map.fitBounds(bounds);

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
                ${s.year1.NDWI.toFixed(4)}
            </span>
            <br>
            MNDWI:
            <span class="success">
                ${s.year1.MNDWI.toFixed(4)}
            </span>
        </div>

        <div class="info-box">
            <b>Năm ${y2Select.value}</b>
            <br><br>
            NDWI:
            <span class="success">
                ${s.year2.NDWI.toFixed(4)}
            </span>
            <br>
            MNDWI:
            <span class="success">
                ${s.year2.MNDWI.toFixed(4)}
            </span>
        </div>

        <div class="info-box">
            🔴 Xói mòn:
            <span class="danger">
                ${s.erosion_ha} ha
            </span>
            <br><br>
            🟢 Bồi tụ:
            <span class="success">
                ${s.accretion_ha} ha
            </span>
        </div>
    `;
}

async function loadForecast() {

    try {

        const province = encodeURIComponent(
            provinceSelect.value
        );

        const res = await fetch(
            `${BASE_URL}/forecast?province=${province}`
        );

        const data = await res.json();

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

        const erosion = s.erosion_ha;
        const accretion = s.accretion_ha;

        const ndwi = (
            s.year1.NDWI +
            s.year2.NDWI
        ) / 2;

        const mndwi = (
            s.year1.MNDWI +
            s.year2.MNDWI
        ) / 2;

        let erosionText = "";
        let ndwiText = "";
        let mndwiText = "";

        if (erosion > accretion) {
            erosionText = `
                Khu vực đang có xu hướng
                <b style="color:red">
                    xói mòn mạnh hơn bồi tụ
                </b>.
                Điều này cho thấy đường bờ biển
                có nguy cơ bị thu hẹp theo thời gian,
                đặc biệt dưới tác động của sóng biển,
                dòng chảy và biến đổi khí hậu.
            `;
        } else if (accretion > erosion) {
            erosionText = `
                Khu vực có xu hướng
                <b style="color:green">
                    bồi tụ mạnh hơn xói mòn
                </b>.
                Điều này phản ánh quá trình tích tụ
                trầm tích đang diễn ra tương đối tốt,
                giúp mở rộng bề mặt ven biển.
            `;
        } else {
            erosionText = `
                Khu vực đang ở trạng thái
                tương đối cân bằng giữa
                xói mòn và bồi tụ.
            `;
        }

        if (ndwi < -0.3) {
            ndwiText = `
                Chỉ số NDWI ở mức thấp,
                phản ánh khu vực có lượng nước bề mặt ít,
                môi trường khô hơn và khả năng hiện diện nước thấp.
            `;
        } else if (ndwi >= -0.3 && ndwi <= 0.3) {
            ndwiText = `
                Chỉ số NDWI ở mức trung bình,
                phản ánh trạng thái chuyển tiếp
                giữa đất và nước hoặc khu vực ẩm ướt.
            `;
        } else {
            ndwiText = `
                Chỉ số NDWI cao,
                cho thấy sự hiện diện mạnh của nước bề mặt,
                vùng ngập nước hoặc khu vực ven biển chịu tác động thủy văn lớn.
            `;
        }

        if (mndwi < -0.3) {
            mndwiText = `
                Chỉ số MNDWI thấp,
                phản ánh khu vực có khả năng chứa nước thấp
                và bề mặt chủ yếu là đất hoặc thực vật.
            `;
        } else if (mndwi >= -0.3 && mndwi <= 0.3) {
            mndwiText = `
                Chỉ số MNDWI ở mức trung bình,
                cho thấy khu vực có sự pha trộn
                giữa nước và đất ngập ẩm.
            `;
        } else {
            mndwiText = `
                Chỉ số MNDWI cao,
                phản ánh khả năng tồn tại nước mặt rõ rệt,
                đặc biệt tại khu vực ven biển hoặc đầm phá.
            `;
        }

        let lastPred =
            data[data.length - 1].prediction;

        let html = `
        <div style="
            line-height:1.9;
            text-align:justify;
            font-size:13px;
        ">

        <b style="
            font-size:15px;
            color:#1e293b;
        ">
            🧠 PHÂN TÍCH AI VEN BIỂN
        </b>

        <br><br>

        Khu vực nghiên cứu:
        <b>${provinceSelect.value}</b>

        <br><br>

        ${erosionText}

        <br><br>

        ${ndwiText}

        <br><br>

        ${mndwiText}

        <br><br>

        AI dự báo rằng đến năm
        <b>${data[data.length - 1].year}</b>
        mức biến động có thể đạt:

        <br><br>

        <div style="
            background:#fee2e2;
            padding:12px;
            border-radius:10px;
            color:#b91c1c;
            font-weight:bold;
            text-align:center;
            font-size:18px;
        ">
            ${Number(lastPred).toFixed(2)} ha
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
                Lỗi tải dự báo AI
            </span>
        `;
    }
}

async function askAI() {

    const question =
        document.getElementById("ai-question").value;

    if (!question) {
        alert("Nhập câu hỏi");
        return;
    }

    if (!resData) {
        alert("Hãy chạy phân tích trước");
        return;
    }

    const answerBox =
        document.getElementById("ai-answer");

    answerBox.innerHTML = "⌛ AI đang phân tích dữ liệu viễn thám...";

    try {

        const res = await fetch(
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

        const data = await res.json();

        if (!res.ok) {
            throw new Error(
                data.error || "Server error"
            );
        }

        if (!data.answer) {
            throw new Error(
                "AI không trả về kết quả"
            );
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
                        s.year1.NDWI,
                        s.year1.MNDWI,
                        s.year2.NDWI,
                        s.year2.MNDWI
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
                        s.erosion_ha,
                        s.accretion_ha
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