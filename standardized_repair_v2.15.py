import os

file_path = r'c:\Users\Emmanuel_PC\Track2Train\Track2Train-staging\templates\index.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# We replace from the first viz script to the very end of </html> to fix everything at once
start_search = '<script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>'

if start_search in content:
    header = content.split(start_search)[0]
    
    new_viz_block = """<script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
    <script>
        (function () {
            function formatPace(minDec) {
                const m = Math.floor(minDec);
                const s = Math.round((minDec - m) * 60);
                return m + ":" + (s < 10 ? "0" + s : s);
            }

            const carousel = document.getElementById('mainCarouselSlides');
            if (!carousel) return;
            const slides = carousel.querySelectorAll('.carousel-slide');
            const totalSlides = slides.length;
            let currentIndex = 0;

            function updateCarousel() {
                slides.forEach((slide, idx) => {
                    if (idx === currentIndex) slide.classList.add('active');
                    else slide.classList.remove('active');
                });
                const indicator = document.getElementById('slideIndicator');
                if (indicator) indicator.textContent = (currentIndex + 1) + " / " + totalSlides;
            }

            document.getElementById('mainPrevBtn')?.addEventListener('click', e => { e.preventDefault(); currentIndex = (currentIndex - 1 + totalSlides) % totalSlides; updateCarousel(); });
            document.getElementById('mainNextBtn')?.addEventListener('click', e => { e.preventDefault(); currentIndex = (currentIndex + 1) % totalSlides; updateCarousel(); });
            document.addEventListener('keydown', e => {
                if (e.key === "ArrowLeft") { currentIndex = (currentIndex - 1 + totalSlides) % totalSlides; updateCarousel(); }
                else if (e.key === "ArrowRight") { currentIndex = (currentIndex + 1) % totalSlides; updateCarousel(); }
            });

            {% for act in activities_for_carousel %}
            (function(idx) {
                try {
                    const labels = {{ act.labels | safe }};
                    const fc = {{ act.points_fc | safe }};
                    const allureCurve = {{ act.allure_curve | safe }};
                    const elevation = {{ act.points_alt | safe }};
                    const hrRest = {{ profile.hr_rest | default(59) }};
                    const hrMax = {{ profile.hr_max | default(170) }};
                    const hrRes = hrMax - hrRest;
                    const z = [0.5, 0.6, 0.7, 0.8, 0.9].map(p => Math.round((hrRes * p) + hrRest));
                    const maxDist = labels.length > 0 ? Math.max(...labels) : 10;

                    // 1. FC Chart
                    new ApexCharts(document.querySelector('#chartFC' + idx), {
                        series: [{ name: 'FC', data: fc.map((v, i) => ({ x: labels[i], y: v })) }],
                        chart: { height: 180, type: 'line', group: 'activity-sync', id: 'chartFC' + idx, toolbar: { show: true }, animations: { enabled: false } },
                        stroke: { width: 1.5, curve: 'smooth' },
                        colors: ['#ef4444'],
                        xaxis: { type: 'numeric', decimalsInFloat: 0, max: maxDist },
                        yaxis: { min: Math.max(80, Math.floor(Math.min(...fc) * 0.95)), max: Math.ceil(Math.max(...fc) * 1.05), tickAmount: 4, labels: { formatter: (val) => Math.round(val) } },
                        annotations: { yaxis: [{ y: z[4], y2: 220, fillColor: '#ef4444', opacity: 0.1 }, { y: z[3], y2: z[4], fillColor: '#f97316', opacity: 0.1 }, { y: z[2], y2: z[3], fillColor: '#facc15', opacity: 0.1 }, { y: z[1], y2: z[2], fillColor: '#22c55e', opacity: 0.1 }, { y: z[0], y2: z[1], fillColor: '#3b82f6', opacity: 0.1 }] }
                    }).render();

                    // 2. Elevation Chart
                    const minAlt = elevation.length > 0 ? Math.min(...elevation) : 0;
                    const relAlt = elevation.map(a => a - minAlt);
                    new ApexCharts(document.querySelector('#chartElevation' + idx), {
                        series: [{ name: 'Altitude', data: relAlt.map((v, i) => ({ x: labels[i], y: v })) }],
                        chart: { height: 180, type: 'area', group: 'activity-sync', id: 'chartElevation' + idx, toolbar: { show: true } },
                        dataLabels: { enabled: false },
                        colors: ['#5D4037'],
                        stroke: { curve: 'smooth', width: 1.5 },
                        fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.7, opacityTo: 0.1, colorStops: [{ offset: 0, color: '#5D4037', opacity: 0.7 }, { offset: 100, color: '#D7CCC8', opacity: 0.1 }] } },
                        xaxis: { type: 'numeric', decimalsInFloat: 1, max: maxDist, title: { text: 'Distance (km)' } },
                        yaxis: { 
                            min: 0, 
                            max: Math.ceil(Math.max(...relAlt, 10) * 1.2), 
                            title: { text: 'Dénivelé (m)' },
                            labels: { formatter: (val) => Math.round(val) }
                        }
                    }).render();

                    // 3. Zones Chart
                    const ctxZ = document.getElementById('chartZones' + idx);
                    if (ctxZ) {
                        const zonesReel = {{ act.zones_reel|tojson|safe if act.zones_reel else "{}" }};
                        const zonesAvg = {{ act.zones_avg|tojson|safe if act.zones_avg else "{}" }};
                        const dataReel = ["1","2","3","4","5"].map(z => zonesReel[z] || 0);
                        const dataAvg = ["1","2","3","4","5"].map(z => zonesAvg[z] || 0);
                        new Chart(ctxZ, {
                            type: 'bar',
                            data: { labels: ['Réel', 'Moy 10'], datasets: [0,1,2,3,4].map(i => ({ label: 'Z'+(i+1), data: [dataReel[i], dataAvg[i]], backgroundColor: ['#3b82f6', '#22c55e', '#facc15', '#f97316', '#ef4444'][i], barThickness: 22 })) },
                            options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, scales: { x: { stacked: true, display: false, max: 100 }, y: { stacked: true, grid: { display: false } } }, plugins: { legend: { display: false }, datalabels: { color: '#fff', font: { size: 9, weight: 'bold' }, formatter: (v) => v > 5 ? Math.round(v) + '%' : '' } } },
                            plugins: [ChartDataLabels]
                        });
                    }

                    // 4. Splits & Pace Stats
                    const splits = [];
                    for(let k=1; k<=Math.ceil(maxDist); k++) {
                        let sP=0, sH=0, c=0;
                        for(let i=0; i<labels.length; i++) { if (labels[i]>=k-1 && labels[i]<k) { sP+=allureCurve[i]; sH+=fc[i]; c++; } }
                        if (c>0) splits.push({ k: Math.min(k, maxDist), p: sP/c, h: sH/c });
                    }
                    const ctxS = document.getElementById('chartAllure' + idx);
                    if (ctxS) {
                        const contS = document.getElementById('chartAllureContainer' + idx);
                        if (contS) contS.style.height = (splits.length * 28 + 60) + 'px';
                        const kmPaces = splits.map(s => s.p);
                        const maxP = kmPaces.length > 0 ? Math.max(...kmPaces) : 6;
                        const minP = kmPaces.length > 0 ? Math.min(...kmPaces) : 4;
                        document.getElementById('allureFastest' + idx).textContent = formatPace(minP) + " /km";
                        document.getElementById('allureSlowest' + idx).textContent = formatPace(maxP) + " /km";
                        new Chart(ctxS, {
                            type: 'bar',
                            data: { labels: splits.map(s => s.k%1===0 ? s.k : s.k.toFixed(1)), datasets: [{ label: 'Pace', data: kmPaces, backgroundColor: '#FC4C02', barThickness: 18 }] },
                            options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, layout: { padding: { right: 150 } }, plugins: { legend: { display: false } }, scales: { x: { position: 'top', min: 3, max: 10, ticks: { display: false }, grid: { display: false } } } },
                            plugins: [{
                                afterDatasetsDraw: (chart) => {
                                    const { ctx, width, scales: { x, y } } = chart;
                                    const xPace = x.getPixelForValue(maxP) + 40;
                                    const xHR = width - 20;
                                    ctx.save(); ctx.font = 'bold 12px Arial'; ctx.textAlign = 'right';
                                    chart.data.datasets[0].data.forEach((val, i) => {
                                        const yPos = y.getPixelForValue(i);
                                        ctx.fillStyle = '#666'; ctx.fillText(formatPace(val), xPace, yPos+4);
                                        if (splits[i].h) { ctx.fillStyle = '#ef4444'; ctx.fillText(Math.round(splits[i].h) + " bpm", xHR, yPos+4); }
                                    });
                                    ctx.restore();
                                }
                            }]
                        });
                    }

                    // 5. Bullet Charts (k and drift)
                                        const setGauge = (id, val, max) => {
                        const el = document.getElementById(id + idx);
                        if (el) el.style.width = Math.min((val / max) * 100, 100) + '%';
                    };
                    const setMarker = (id, val, max) => {
                        const el = document.getElementById(id + idx);
                        if (el) el.style.left = Math.min((val / max) * 100, 100) + '%';
                    };

                    setTimeout(() => {
                        setGauge('gaugeK', {{ act.k_moy | default(0) }}, 10);
                        setMarker('markerTargetK', {{ personalized_targets[act.session_category].k_target if (personalized_targets and act.session_category in personalized_targets) else 0 }}, 10);
                        setMarker('markerAvgK', {{ act.k_avg_10 | default(0) }}, 10);

                        setGauge('gaugeDrift', {{ act.deriv_cardio | default(0) }}, 20);
                        setMarker('markerTargetDrift', {{ personalized_targets[act.session_category].drift_target if (personalized_targets and act.session_category in personalized_targets) else 0 }}, 20);
                        setMarker('markerAvgDrift', {{ act.drift_avg_10 | default(0) }}, 20);
                    }, 500);

                } catch(e) { console.error("Slide error:", idx, e); }
            })({{ loop.index0 }});
            {% endfor %}

            updateCarousel();
        })();

        async function generateAIComment(button) {
            const activityDate = button.dataset.activityDate;
            const slideIndex = button.dataset.slideIndex;
            const commentDiv = document.getElementById(`ai-comment-${slideIndex}`);
            button.disabled = true; button.innerHTML = '⏳ Génération...';
            try {
                const response = await fetch(`/generate_ai_comment/${activityDate}`);
                const data = await response.json();
                if (data.success) { commentDiv.style.display = 'block'; commentDiv.innerHTML = data.comment; button.innerHTML = '🔄 Regénérer'; }
                else { commentDiv.style.display = 'block'; commentDiv.innerHTML = `<p>⚠️ ${data.error}</p>`; button.innerHTML = '🔄 Réessayer'; }
            } catch (e) { commentDiv.style.display = 'block'; commentDiv.innerHTML = '<p>❌ Erreur</p>'; button.innerHTML = '🔄 Réessayer'; }
            button.disabled = false;
        }
        function showCoachingInfo() { document.getElementById('coaching-info-modal').style.display = 'flex'; }
        function closeCoachingInfo() { document.getElementById('coaching-info-modal').style.display = 'none'; }
        window.onclick = e => { if (e.target.id === 'coaching-info-modal') closeCoachingInfo(); };
    </script>

    <!-- Modal Informations Coaching -->
    {% set birth_year = profile.birth_date[:4]|int if profile.birth_date else 1973 %}
    {% set age = 2025 - birth_year %}
    {% set main_goal_text = "Semi-Marathon" if profile.objectives.main_goal == "semi_marathon" else profile.objectives.main_goal|title if profile.objectives and profile.objectives.main_goal else "Semi-Marathon" %}

    <div id="coaching-info-modal" style="display: none; position: fixed; z-index: 9999; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); align-items: center; justify-content: center;">
        <div style="background-color: white; padding: 2rem; border-radius: 12px; max-width: 600px; max-height: 85vh; overflow-y: auto; margin: 1rem; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                <h2 style="margin: 0; color: #1a73e8; font-size: 1.5rem;">ℹ️ Guide Coaching IA</h2>
                <button onclick="closeCoachingInfo()" style="background: none; border: none; font-size: 1.5rem; cursor: pointer; color: #666;">&times;</button>
            </div>
            <div style="line-height: 1.7;">
                <p><strong>Cible {{ main_goal_text }} :</strong> k ~5.2-5.4.</p>
                <p><strong>Drift :</strong> <3% Récupération, 4-6% Tempo, 6-9% Long Run.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
    final_content = header + new_viz_block
    
    # Final cleanup of split tags
    final_content = final_content.replace("{ {", "{{").replace("} }", "}}")

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)
    print("Unified repair successful.")
else:
    print("Start marker not found!")
