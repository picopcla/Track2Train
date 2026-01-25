import re

file_path = r'c:\Users\Emmanuel_PC\Track2Train\Track2Train-staging\templates\index.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Identify the block to replace. 
# We'll use a broad match from the carousel script start to the next distinct script block.
start_marker = "// CARROUSEL PRINCIPAL"
end_marker = "<!-- JavaScript pour les jauges Bullet Chart k et drift -->"

if start_marker in content and end_marker in content:
    header = content.split(start_marker)[0]
    middle = content.split(start_marker)[1].split(end_marker)[0]
    footer = content.split(end_marker)[1]
    
    # We will generate a CLEAN version of the middle part.
    # Note: I am including the carousel navigation and the loop for charts.
    
    new_middle = """
        (function () {
            const carousel = document.getElementById('mainCarouselSlides');
            if (!carousel) return;
            const slides = carousel.querySelectorAll('.carousel-slide');
            const prevBtn = document.getElementById('mainPrevBtn');
            const nextBtn = document.getElementById('mainNextBtn');
            const totalSlides = slides.length;
            let currentIndex = 0;

            function updateCarousel() {
                // Mettre à jour les slides (show/hide via classe active)
                slides.forEach((slide, idx) => {
                    if (idx === currentIndex) {
                        slide.classList.add('active');
                    } else {
                        slide.classList.remove('active');
                    }
                });
                
                // Mettre à jour l'indicateur textuel s'il existe
                const indicator = document.getElementById('slideIndicator');
                if (indicator) {
                    indicator.textContent = `${currentIndex + 1} / ${totalSlides}`;
                }
            }

            if (prevBtn) {
                prevBtn.addEventListener('click', () => {
                    currentIndex = (currentIndex - 1 + totalSlides) % totalSlides;
                    updateCarousel();
                });
            }

            if (nextBtn) {
                nextBtn.addEventListener('click', () => {
                    currentIndex = (currentIndex + 1) % totalSlides;
                    updateCarousel();
                });
            }

            // Swipe / Touch - Pour mobile (optionnel mais utile si on veut garder le swipe)
            let touchStartX = 0;
            let touchEndX = 0;
            carousel.addEventListener('touchstart', e => {
                touchStartX = e.changedTouches[0].screenX;
            }, {passive: true});
            carousel.addEventListener('touchend', e => {
                touchEndX = e.changedTouches[0].screenX;
                if (touchStartX - touchEndX > 50) {
                    currentIndex = (currentIndex + 1) % totalSlides;
                    updateCarousel();
                } else if (touchEndX - touchStartX > 50) {
                    currentIndex = (currentIndex - 1 + totalSlides) % totalSlides;
                    updateCarousel();
                }
            }, {passive: true});

            updateCarousel();

            // Création des graphiques ApexCharts pour chaque slide
            {% for act in activities_for_carousel %}
            (function(idx) {
                const labels = {{ act.labels | safe }};
                const fc = {{ act.points_fc | safe }};
                const allure = {{ act.allure_curve | safe }};
                const elevationData = {{ act.points_alt | safe }};

                const minElevation = elevationData.length > 0 ? Math.min(...elevationData) : 0;
                const maxElevation = elevationData.length > 0 ? Math.max(...elevationData) : 100;
                const fcMax = fc.length > 0 ? Math.max(...fc) : 180;
                const allureMax = allure.length > 0 ? Math.max(...allure) : 8;

                const allureMaxMin = Math.floor(allureMax);
                const allureMaxSec = Math.round((allureMax - allureMaxMin) * 60);
                const allureMaxElement = document.getElementById('allureMax' + idx);
                if (allureMaxElement) {
                    allureMaxElement.textContent = allureMaxMin + ':' + (allureMaxSec < 10 ? '0' : '') + allureMaxSec + ' /km';
                }

                const fcMin = fc.length > 0 ? Math.min(...fc) : 100;
                const hrRest = {{ profile.hr_rest | default(59) }};
                const hrMax = {{ profile.hr_max | default(170) }};
                const hrReserve = hrMax - hrRest;

                const z0 = Math.round((hrReserve * 0.5) + hrRest);
                const z1 = Math.round((hrReserve * 0.6) + hrRest);
                const z2 = Math.round((hrReserve * 0.7) + hrRest);
                const z3 = Math.round((hrReserve * 0.8) + hrRest);
                const z4 = Math.round((hrReserve * 0.9) + hrRest);

                const maxDistance = labels.length > 0 ? Math.max(...labels) : 10;
                const tickInterval = maxDistance < 5 ? 0.5 : 1;
                const tickAmount = Math.floor(maxDistance / tickInterval);

                const optionsFC = {
                    series: [{
                        name: 'FC',
                        data: fc.map((val, i) => ({ x: labels[i], y: val }))
                    }],
                    chart: {
                        height: 180,
                        type: 'line',
                        group: 'activity-sync',
                        id: 'chartFC' + idx,
                        toolbar: { show: true },
                        zoom: { enabled: true },
                        animations: { enabled: false }
                    },
                    stroke: { width: 2, curve: 'smooth' },
                    colors: ['#ef4444'],
                    xaxis: { 
                        type: 'numeric', 
                        decimalsInFloat: 1, 
                        min: 0, 
                        max: maxDistance,
                        labels: { style: { fontSize: '12px' } }
                    },
                    yaxis: {
                        min: Math.max(90, Math.floor(fcMin * 0.92)),
                        max: Math.ceil(fcMax * 1.02),
                        tickAmount: 4,
                        labels: { style: { fontSize: '11px', fontWeight: 'bold' } }
                    },
                    annotations: {
                        yaxis: [
                            { y: z4, y2: hrMax * 1.1, fillColor: '#ef4444', opacity: 0.25 },
                            { y: z3, y2: z4, fillColor: '#f97316', opacity: 0.25 },
                            { y: z2, y2: z3, fillColor: '#facc15', opacity: 0.25 },
                            { y: z1, y2: z2, fillColor: '#22c55e', opacity: 0.25 },
                            { y: z0, y2: z1, fillColor: '#3b82f6', opacity: 0.25 }
                        ]
                    },
                    tooltip: { y: { formatter: (val) => Math.round(val) + ' bpm' } }
                };

                const chartFC = new ApexCharts(document.querySelector('#chartFC' + idx), optionsFC);
                chartFC.render();

                // Elevation chart
                const altitudeRelative = elevationData.map(alt => alt - minElevation);
                const altRelMax = Math.max(...altitudeRelative, 10);
                
                const optionsElevation = {
                    series: [{ name: 'Élévation', data: altitudeRelative.map((val, i) => ({ x: labels[i], y: val })) }],
                    chart: { height: 140, type: 'area', group: 'activity-sync', id: 'chartElevation' + idx, toolbar: { show: true } },
                    stroke: { curve: 'smooth', width: 2 },
                    fill: { type: 'gradient', gradient: { opacityFrom: 0.6, opacityTo: 0.1 } },
                    xaxis: { type: 'numeric', min: 0, max: maxDistance },
                    yaxis: { min: 0, max: Math.ceil(altRelMax * 1.1), forceNiceScale: true },
                    tooltip: { y: { formatter: (val) => Math.round(val) + ' m' } }
                };
                
                const chartElevation = new ApexCharts(document.querySelector('#chartElevation' + idx), optionsElevation);
                chartElevation.render();

                // Chart.js Allure per KM
                setTimeout(() => {
                    const ctx = document.getElementById('chartAllure' + idx);
                    if (!ctx) return;
                    
                    const splits = [];
                    for(let k=1; k<=Math.ceil(maxDistance); k++) {
                        const distLimit = Math.min(k, maxDistance);
                        let sumPace = 0, count = 0;
                        for(let i=0; i<labels.length; i++) {
                            if (labels[i] >= k-1 && labels[i] < k) {
                                sumPace += allure[i];
                                count++;
                            }
                        }
                        if (count > 0) splits.push({ km: distLimit, pace: sumPace/count });
                    }

                    const container = document.getElementById('chartAllureContainer' + idx);
                    if (container) container.style.height = (splits.length * 30 + 50) + 'px';

                    new Chart(ctx, {
                        type: 'bar',
                        data: {
                            labels: splits.map(s => s.km % 1 === 0 ? s.km : s.km.toFixed(1)),
                            datasets: [{
                                label: 'Allure (min/km)',
                                data: splits.map(s => s.pace),
                                backgroundColor: '#FC4C02',
                                barThickness: 20
                            }]
                        },
                        options: {
                            indexAxis: 'y',
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false } },
                            scales: {
                                x: { position: 'top', min: 3, max: 10 },
                                y: { ticks: { font: { weight: 'bold' } } }
                            }
                        }
                    });
                }, 500);

            })({{ loop.index0 }});
            {% endfor %}
        })();
    """

    
    final_content = header + start_marker + new_middle + end_marker + footer
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)
    print("Carousel repair successful.")
else:
    print("Markers not found. Check the file structure.")
