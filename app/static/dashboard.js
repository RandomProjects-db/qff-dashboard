/* Dashboard charts + table search. Reads server-rendered stats from a JSON
   script tag (no registrant PII is sent here beyond aggregate counts). */
(function () {
  "use strict";

  const stats = JSON.parse(document.getElementById("stats-data").textContent);

  const PINK = "#ff006b";
  const CYAN = "#00e5ff";
  const PURPLE = "#6929c4";
  const AMBER = "#f5a623";
  const GRID = "rgba(255,255,255,0.06)";
  const TICK = "rgba(244,246,251,0.6)";

  Chart.defaults.color = TICK;
  Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

  const noLegend = { plugins: { legend: { display: false } } };
  const gridScales = {
    scales: {
      x: { grid: { color: GRID }, ticks: { color: TICK } },
      y: { grid: { color: GRID }, ticks: { color: TICK }, beginAtZero: true },
    },
  };

  function keys(obj) { return Object.keys(obj || {}); }
  function vals(obj) { return Object.values(obj || {}); }

  // Registrations over time (line)
  new Chart(document.getElementById("timelineChart"), {
    type: "line",
    data: {
      labels: keys(stats.timeline),
      datasets: [{
        data: vals(stats.timeline),
        borderColor: PINK,
        backgroundColor: "rgba(255,0,107,0.15)",
        fill: true,
        tension: 0.3,
        pointRadius: 3,
      }],
    },
    options: Object.assign({ responsive: true }, noLegend, gridScales),
  });

  // Attendance format (doughnut)
  new Chart(document.getElementById("formatChart"), {
    type: "doughnut",
    data: {
      labels: ["In-Person", "Virtual"],
      datasets: [{
        data: [stats.in_person, stats.virtual],
        backgroundColor: [PINK, CYAN],
        borderColor: "#0d1220",
        borderWidth: 2,
      }],
    },
    options: { responsive: true, plugins: { legend: { position: "bottom" } } },
  });

  // Days attending (bar)
  new Chart(document.getElementById("daysChart"), {
    type: "bar",
    data: {
      labels: keys(stats.days_attending),
      datasets: [{ data: vals(stats.days_attending), backgroundColor: PURPLE, borderRadius: 6 }],
    },
    options: Object.assign({ responsive: true }, noLegend, gridScales),
  });

  // Experience level (bar)
  new Chart(document.getElementById("expChart"), {
    type: "bar",
    data: {
      labels: keys(stats.exp_buckets),
      datasets: [{ data: vals(stats.exp_buckets), backgroundColor: AMBER, borderRadius: 6 }],
    },
    options: Object.assign({ responsive: true }, noLegend, gridScales),
  });

  // Hackathon interest (doughnut)
  new Chart(document.getElementById("hackChart"), {
    type: "doughnut",
    data: {
      labels: keys(stats.hackathon),
      datasets: [{
        data: vals(stats.hackathon),
        backgroundColor: [PINK, AMBER, "#4a5568"],
        borderColor: "#0d1220",
        borderWidth: 2,
      }],
    },
    options: { responsive: true, plugins: { legend: { position: "bottom" } } },
  });

  // How they heard (horizontal bar)
  new Chart(document.getElementById("heardChart"), {
    type: "bar",
    data: {
      labels: keys(stats.how_heard),
      datasets: [{ data: vals(stats.how_heard), backgroundColor: CYAN, borderRadius: 6 }],
    },
    options: Object.assign({ responsive: true, indexAxis: "y" }, noLegend, gridScales),
  });

  // Table search
  const search = document.getElementById("tableSearch");
  const rows = Array.from(document.querySelectorAll("#regTable tbody tr"));
  search.addEventListener("input", function () {
    const q = search.value.trim().toLowerCase();
    rows.forEach((tr) => {
      tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  });
})();
