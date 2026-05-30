let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth() + 1;

$(function () {
    showPage("calendar");

    loadCalendar(currentYear, currentMonth);

    $("#exportGmailBtn").click(function () {
        showLoading();

        fetch("/api/export-gmail", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                days: 30,
                limit: 50,
                primary: true
            })
        })
            .then(res => res.json().then(data => ({
                ok: res.ok,
                data: data
            })))
            .then(result => {
                hideLoading();

                if (!result.ok) {
                    alert(result.data.error || "匯出 Gmail 資料失敗");
                    return;
                }

                alert(result.data.message || "Gmail 資料已更新");
            })
            .catch(error => {
                console.error(error);
                alert("系統發生錯誤，請稍後再試");
                hideLoading();
            });
    });

    $("#prev").click(function () {
        currentMonth--;

        if (currentMonth === 0) {
            currentMonth = 12;
            currentYear--;
        }

        loadCalendar(currentYear, currentMonth);
    });

    $("#next").click(function () {
        currentMonth++;

        if (currentMonth === 13) {
            currentMonth = 1;
            currentYear++;
        }

        loadCalendar(currentYear, currentMonth);
    });

    $("#exitSummary").click(function () {
        showPage("calendar");
    });
});


function loadCalendar(year, month) {
    fetch(`/api/calendar/${year}/${month}`)
        .then(res => res.json())
        .then(data => {
            currentYear = data.year;
            currentMonth = data.month;

            renderCalendar(data);
        });
}


function renderCalendar(data) {
    $("#yearLabel").text(data.year);
    $("#monthLabel").text(data.month);

    let html = "";

    data.cal_data.forEach(week => {
        week.forEach(day => {

            if (day === 0) {
                html += `<div class="calendar-day empty"></div>`;
            } else {
                html += `<div class="calendar-day">${day}</div>`;
            }

        });
    });

    $("#calendarGrid").html(html);
    $(".calendar-day:not(.empty)").click(function () {
        showLoading();

        fetch(`/api/summary/${currentYear}/${currentMonth}/${$(this).text()}`)
            .then(res => res.json().then(data => ({
                ok: res.ok,
                data: data
            })))
            .then(result => {
                if (!result.ok) {
                    alert(result.data.error || "讀取摘要失敗");
                    hideLoading();
                    return;
                }

                const data = result.data;
                const timestamp = Date.now();

                $("#summaryText").text(data.summary);

                // 更新成該日期的文字雲圖片，避免顯示上一個日期的快取。
                $("#summaryPage img").attr("src", `${data.wordcloud_path}?t=${timestamp}`);

                // 更新成該日期的 MP3。
                $("#summaryPage audio source").attr("src", `${data.audio_path}?t=${timestamp}`);
                $("#summaryPage audio")[0].load();

                showPage("summary");
                hideLoading();
            })
            .catch(error => {
                console.error(error);
                alert("系統發生錯誤，請稍後再試");
                hideLoading();
            });
    });
}

function showPage(page) {
    if (page === "calendar") {
        $("#summaryPage").removeClass("active");
        $("#calendarPage").addClass("active");
    }

    if (page === "summary") {
        $("#calendarPage").removeClass("active");
        $("#summaryPage").addClass("active");
    }
}

function showLoading() {
    $("#loading").addClass("active");
}

function hideLoading() {
    $("#loading").removeClass("active");
}
