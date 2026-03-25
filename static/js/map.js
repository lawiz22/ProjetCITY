function formatNumber(value) {
    return new Intl.NumberFormat('fr-CA').format(value || 0);
}

function buildCityDetailUrl(citySlug, annotationYear = null) {
    const params = new URLSearchParams(window.location.search);
    const forwarded = new URLSearchParams();
    ['country', 'region', 'period', 'search'].forEach((key) => {
        const value = params.get(key);
        if (value) {
            forwarded.set(key, value);
        }
    });
    if (annotationYear) {
        forwarded.set('focus_annotation', annotationYear);
    }
    const queryString = forwarded.toString();
    return `/cities/${citySlug}${queryString ? `?${queryString}` : ''}`;
}

function buildPopup(point, theme) {
    const growth = point.latest_growth_pct === null || point.latest_growth_pct === undefined
        ? 'n/a'
        : `${point.latest_growth_pct}% (${point.latest_growth_decade})`;

    const annotationHtml = (point.annotations || []).length > 0
        ? `<div class="map-popup-annotations">${point.annotations.map((annotation) => `<button type="button" class="map-popup-annotation" data-city-slug="${point.city_slug}" data-annotation-year="${annotation.year}"><span style="background:${annotation.color}"></span>${annotation.year} · ${annotation.label}</button>`).join('')}</div>`
        : '<p>Aucune annotation détaillée disponible.</p>';

    const themeBlock = theme === 'annotations'
        ? `<div class="map-popup-layer"><strong>Annotations temporelles</strong>${annotationHtml}</div>`
        : '';

    return `
        <div class="map-popup">
            <h3>${point.city_name}</h3>
            <p>${point.country} · ${point.region}</p>
            <p>Population récente: ${formatNumber(point.population)} en ${point.year}</p>
            <p>Pic: ${point.peak_population ? `${formatNumber(point.peak_population)} en ${point.peak_year}` : 'n/a'}</p>
            <p>Croissance récente: ${growth}</p>
            ${themeBlock}
            <a href="${buildCityDetailUrl(point.city_slug)}">Ouvrir la fiche</a>
        </div>
    `;
}

function themeLabel(theme) {
    const labels = {
        population: 'Population',
        growth: 'Croissance',
        decline: 'Déclin',
        peak: 'Pics',
        annotations: 'Annotations'
    };
    return labels[theme] || 'Population';
}

function markerStyle(point, theme) {
    if (theme === 'growth') {
        const growth = point.latest_growth_pct || 0;
        return {
            radius: Math.max(8, Math.min(26, 10 + Math.abs(growth) / 4)),
            color: growth >= 0 ? '#1f9d66' : '#b33951',
            fillColor: growth >= 0 ? '#1f9d66' : '#b33951'
        };
    }
    if (theme === 'decline') {
        const declineCount = point.decline_count || 0;
        return {
            radius: Math.max(8, Math.min(24, 8 + declineCount * 3)),
            color: declineCount > 0 ? '#b33951' : '#b8c0cc',
            fillColor: declineCount > 0 ? '#b33951' : '#b8c0cc'
        };
    }
    if (theme === 'peak') {
        const peakPopulation = point.peak_population || point.population || 0;
        return {
            radius: Math.max(8, Math.min(28, 8 + peakPopulation / 500000)),
            color: '#264653',
            fillColor: '#264653'
        };
    }
    if (theme === 'annotations') {
        const annotationCount = point.annotation_count || 0;
        return {
            radius: Math.max(8, Math.min(24, 8 + annotationCount * 2)),
            color: annotationCount > 0 ? '#ef6c3d' : '#b8c0cc',
            fillColor: annotationCount > 0 ? '#ef6c3d' : '#b8c0cc'
        };
    }
    return {
        radius: point.radius,
        color: point.city_color,
        fillColor: point.city_color
    };
}

function mountMap(element) {
    if (!window.L) {
        return;
    }

    const rawPayload = element.dataset.map;
    if (!rawPayload) {
        return;
    }

    const points = JSON.parse(rawPayload);
    const countrySelect = document.getElementById('map-country-filter');
    const regionSelect = document.getElementById('map-region-filter');
    const themeSelect = document.getElementById('map-theme-filter');
    const populationFilter = document.getElementById('map-population-filter');
    const populationValue = document.getElementById('map-population-value');
    const searchFilter = document.getElementById('map-search-filter');
    const summary = document.getElementById('map-visible-summary');
    const resetButton = document.getElementById('map-reset-filters');
    const map = L.map(element, {
        scrollWheelZoom: true,
        minZoom: 3
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    const markerLayer = L.layerGroup().addTo(map);
    const allCountries = [...new Set(points.map((point) => point.country))].sort();
    const allRegions = [...new Set(points.map((point) => point.region))].sort();

    allCountries.forEach((country) => {
        const option = document.createElement('option');
        option.value = country;
        option.textContent = country;
        countrySelect.appendChild(option);
    });

    allRegions.forEach((region) => {
        const option = document.createElement('option');
        option.value = region;
        option.textContent = region;
        regionSelect.appendChild(option);
    });

    function renderMarkers() {
        const selectedCountry = countrySelect.value;
        const selectedRegion = regionSelect.value;
        const selectedTheme = themeSelect.value || 'population';
        const minPopulation = Number(populationFilter.value || 0);
        const searchTerm = (searchFilter.value || '').trim().toLowerCase();

        populationValue.textContent = formatNumber(minPopulation);
        markerLayer.clearLayers();

        const visiblePoints = points.filter((point) => {
            if (selectedCountry && point.country !== selectedCountry) {
                return false;
            }
            if (selectedRegion && point.region !== selectedRegion) {
                return false;
            }
            if (point.population < minPopulation) {
                return false;
            }
            if (searchTerm && !point.city_name.toLowerCase().includes(searchTerm)) {
                return false;
            }
            return true;
        });

        const bounds = [];
        visiblePoints.forEach((point) => {
            const style = markerStyle(point, selectedTheme);
            const marker = L.circleMarker([point.lat, point.lng], {
                radius: style.radius,
                color: style.color,
                fillColor: style.fillColor,
                fillOpacity: 0.42,
                weight: 2
            });
            marker.bindPopup(buildPopup(point, selectedTheme));
            marker.addTo(markerLayer);
            bounds.push([point.lat, point.lng]);
        });

        if (summary) {
            summary.textContent = `${visiblePoints.length} villes visibles. Couche active: ${themeLabel(selectedTheme)}.`;
        }

        if (bounds.length > 0) {
            map.fitBounds(bounds, { padding: [28, 28], maxZoom: 7 });
        } else {
            map.setView([45.5, -96], 4);
        }
    }

    [countrySelect, regionSelect, themeSelect, populationFilter, searchFilter].forEach((elementRef) => {
        elementRef.addEventListener('input', renderMarkers);
        elementRef.addEventListener('change', renderMarkers);
    });

    resetButton.addEventListener('click', () => {
        countrySelect.value = '';
        regionSelect.value = '';
        themeSelect.value = 'population';
        populationFilter.value = '0';
        searchFilter.value = '';
        renderMarkers();
    });

    renderMarkers();

    map.on('popupopen', (event) => {
        const popupElement = event.popup.getElement();
        if (!popupElement) {
            return;
        }
        popupElement.querySelectorAll('.map-popup-annotation').forEach((button) => {
            button.addEventListener('click', () => {
                const citySlug = button.dataset.citySlug;
                const annotationYear = button.dataset.annotationYear;
                if (citySlug && annotationYear) {
                    window.location.href = buildCityDetailUrl(citySlug, annotationYear);
                }
            });
        });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const element = document.getElementById('city-map');
    if (element) {
        mountMap(element);
    }
});