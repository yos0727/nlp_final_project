let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth() + 1;

$(function () {
    showPage("calendar");

    loadCalendar(currentYear, currentMonth);

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
            .then(res => res.json())
            .then(data => {
                $("#summaryText").text(data.summary);
                showPage("summary");
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