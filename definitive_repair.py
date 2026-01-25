import re
import os

file_path = r'c:\Users\Emmanuel_PC\Track2Train\Track2Train-staging\templates\index.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Markers for the broken script block
start_marker = "// CARROUSEL PRINCIPAL"
end_marker = "<!-- JavaScript pour les jauges Bullet Chart k et drift -->"

if start_marker in content and end_marker in content:
    parts = content.split(start_marker)
    header = parts[0]
    rest = parts[1].split(end_marker)
    footer = rest[1]
    
    new_script = """
        (function () {
            const carousel = document.getElementById('mainCarouselSlides');
            if (!carousel) return;
            const slides = carousel.querySelectorAll('.carousel-slide');
            const prevBtn = document.getElementById('mainPrevBtn');
            const nextBtn = document.getElementById('mainNextBtn');
            const totalSlides = slides.length;
            let currentIndex = 0;

            function updateCarousel() {
                // Show/hide via active class
                slides.forEach((slide, idx) => {
                    if (idx === currentIndex) {
                        slide.classList.add('active');
                    } else {
                        slide.classList.remove('active');
                    }
                });
                
                const indicator = document.getElementById('slideIndicator');
                if (indicator) {
                    indicator.textContent = (currentIndex + 1) + " / " + totalSlides;
                }
            }

            if (prevBtn) {
                prevBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    currentIndex = (currentIndex - 1 + totalSlides) % totalSlides;
                    updateCarousel();
                });
            }

            if (nextBtn) {
                nextBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    currentIndex = (currentIndex + 1) % totalSlides;
                    updateCarousel();
                });
            }

            // Keyboard navigation
            document.addEventListener('keydown', function(e) {
                if (e.key === "ArrowLeft") {
                    currentIndex = (currentIndex - 1 + totalSlides) % totalSlides;
                    updateCarousel();
                } else if (e.key === "ArrowRight") {
                    currentIndex = (currentIndex + 1) % totalSlides;
                    updateCarousel();
                }
            });

            {% for act in activities_for_carousel %}
            (function(idx) {
                try {
                    const labels = {{ act.labels | safe }};
                    const fc = {{ act.points_fc | safe }};
                    const allure = {{ act.allure_curve | safe }};
                    const elevationData = {{ act.points_alt | safe }};

                    const fcMin = fc.length > 0 ? Math.min(...fc) : 100;
                    const fcMax = fc.length > 0 ? Math.max(...fc) : 180;
                    const allureMax = allure.length > 0 ? Math.max(...allure) : 8;

                    const allureMaxElement = document.getElementById('allureMax' + idx);
                    if (allureMaxElement) {
                        const min = Math.floor(allureMax);
                        const sec = Math.round((allureMax - min) * 60);
                        allureMaxElement.textContent = min + ':' + (sec < 10 ? '0' : '') + sec + ' /km';
                    }

                    const hrRest = {{ profile.hr_rest | default(59) }};
                    const hrMax = {{ profile.hr_max | default(170) }};
                    const hrReserve = hrMax - hrRest;

                    const z0 = Math.round((hrReserve * 0.5) + hrRest);
                    const z1 = Math.round((hrReserve * 0.6) + hrRest);
                    const z2 = Math.round((hrReserve * 0.7) + hrRest);
                    const z3 = Math.round((hrReserve * 0.8) + hrRest);
                    const z4 = Math.round((hrReserve * 0.9) + hrRest);

                    const maxDistance = labels.length > 0 ? Math.max(...labels) : 10;

                    // ApexCharts FC
                    const optionsFC = {
                        series: [{ name: 'FC', data: fc.map((val, i) => ({ x: labels[i], y: val })) }],
                        chart: { height: 180, type: 'line', group: 'activity-sync', id: 'chartFC' + idx, toolbar: { show: true }, zoom: { enabled: true }, animations: { enabled: false } },
                        stroke: { width: 2, curve: 'smooth' },
                        colors: ['#ef4444'],
                        xaxis: { type: 'numeric', decimalsInFloat: 1, min: 0, max: maxDistance },
                        yaxis: { min: Math.max(90, Math.floor(fcMin * 0.92)), max: Math.ceil(fcMax * 1.02), tickAmount: 4 },
                        annotations: {
                            yaxis: [
                                { y: z4, y2: hrMax * 1.1, fillColor: '#ef4444', opacity: 0.2 },
                                { y: z3, y2: z4, fillColor: '#f97316', opacity: 0.2 },
                                { y: z2, y2: z3, fillColor: '#facc15', opacity: 0.2 },
                                { y: z1, y2: z2, fillColor: '#22c55e', opacity: 0.2 },
                                { y: z0, y2: z1, fillColor: '#3b82f6', opacity: 0.2 }
                            ]
                        },
                        tooltip: { y: { formatter: (val) => Math.round(val) + ' bpm' } }
                    };
                    new ApexCharts(document.querySelector('#chartFC' + idx), optionsFC).render();

                    // ApexCharts Elevation
                    const minAlt = elevationData.length > 0 ? Math.min(...elevationData) : 0;
                    const altRel = elevationData.map(a => a - minAlt);
                    const optionsElevation = {
                        series: [{ name: 'Elevation', data: altRel.map((val, i) => ({ x: labels[i], y: val })) }],
                        chart: { height: 140, type: 'area', group: 'activity-sync', id: 'chartElevation' + idx, toolbar: { show: true } },
                        stroke: { curve: 'smooth', width: 2 },
                        fill: { type: 'gradient', gradient: { opacityFrom: 0.5, opacityTo: 0.1 } },
                        xaxis: { type: 'numeric', min: 0, max: maxDistance },
                        yaxis: { min: 0, max: Math.max(...altRel, 10) * 1.1 }
                    };
                    new ApexCharts(document.querySelector('#chartElevation' + idx), optionsElevation).render();

                    // Chart.js Allure Splits
                    const splitData = [];
                    for(let k=1; k<=Math.ceil(maxDistance); k++) {
                        let sum = 0, count = 0;
                        for(let i=0; i<labels.length; i++) {
                            if (labels[i] >= k-1 && labels[i] < k) { sum += allure[i]; count++; }
                        }
                        if (count > 0) splitData.push({ km: Math.min(k, maxDistance), pace: sum/count });
                    }

                    const ctxSplit = document.getElementById('chartAllure' + idx);
                    if (ctxSplit) {
                        const containerSplit = document.getElementById('chartAllureContainer' + idx);
                        if (containerSplit) containerSplit.style.height = (splitData.length * 28 + 60) + 'px';
                        new Chart(ctxSplit, {
                            type: 'bar',
                            data: {
                                labels: splitData.map(s => s.km % 1 === 0 ? s.km : s.km.toFixed(1)),
                                datasets: [{ label: 'Pace', data: splitData.map(s => s.pace), backgroundColor: '#FC4C02', barThickness: 18 }]
                            },
                            options: {
                                indexAxis: 'y',
                                responsive: true,
                                maintainAspectRatio: false,
                                plugins: { legend: { display: false } },
                                scales: { x: { position: 'top', min: 3, max: 10 } }
                            }
                        });
                    }
                } catch(e) { console.error("Error initializing charts for slide " + idx, e); }
            })({{ loop.index0 }});
            {% endfor %}

            updateCarousel();
        })();
    """

    final_content = header + start_marker + new_script + end_marker + footer
    
    # Pre-emptive fix for common corruption patterns that might exist outside the marker block
    final_content = final_content.replace("{ {", "{{").replace("} }", "}}")

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)
    print("Definitive Carousel Repair successful.")
else:
    print("Markers not found! HTML structure might be too corrupted.")
