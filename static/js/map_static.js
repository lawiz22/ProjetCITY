function formatMapNumber(value) {
    return new Intl.NumberFormat('fr-CA').format(Number(value || 0));
}

function getStaticMarkerStyle(link, theme) {
    const cityColor = link.dataset.cityColor || '#2f6fed';
    const growthPct = Number(link.dataset.growthPct || 0);
    const declineCount = Number(link.dataset.declineCount || 0);
    const annotationCount = Number(link.dataset.annotationCount || 0);
    const peakPopulation = Number(link.dataset.peakPopulation || link.dataset.population || 0);
    const baseRadius = Number(link.dataset.baseRadius || 10);

    if (theme === 'growth') {
        return {
            color: growthPct >= 0 ? '#1f9d66' : '#b33951',
            radius: Math.max(9, Math.min(24, 10 + Math.abs(growthPct) / 4))
        };
    }

    if (theme === 'decline') {
        return {
            color: declineCount > 0 ? '#b33951' : '#b8c0cc',
            radius: Math.max(9, Math.min(22, 9 + declineCount * 2.5))
        };
    }

    if (theme === 'peak') {
        return {
            color: '#264653',
            radius: Math.max(10, Math.min(26, 10 + peakPopulation / 500000))
        };
    }

    if (theme === 'annotations') {
        return {
            color: annotationCount > 0 ? '#ef6c3d' : '#b8c0cc',
            radius: Math.max(9, Math.min(22, 9 + annotationCount * 2))
        };
    }

    return { color: cityColor, radius: baseRadius };
}

function applyStaticMarkerStyle(link, theme) {
    const style = getStaticMarkerStyle(link, theme);
    const halo = link.querySelector('.map-point-halo');
    const ring = link.querySelector('.map-point-ring');
    const core = link.querySelector('.map-point-core');

    if (!halo || !ring || !core) {
        return;
    }

    halo.setAttribute('r', String(style.radius + 4));
    halo.setAttribute('fill', style.color);
    halo.setAttribute('fill-opacity', '0.18');

    ring.setAttribute('r', String(style.radius));
    ring.setAttribute('fill', style.color);
    ring.setAttribute('fill-opacity', '0.34');
    ring.setAttribute('stroke', style.color);
    ring.setAttribute('stroke-width', '2');

    core.setAttribute('fill', style.color);
}

document.addEventListener('DOMContentLoaded', () => {
    const mapElement = document.getElementById('city-map');
    if (!mapElement) {
        return;
    }

    const pointLinks = Array.from(mapElement.querySelectorAll('.map-point-link'));
    const countrySelect = document.getElementById('map-country-filter');
    const regionSelect = document.getElementById('map-region-filter');
    const themeSelect = document.getElementById('map-theme-filter');
    const populationFilter = document.getElementById('map-population-filter');
    const populationValue = document.getElementById('map-population-value');
    const searchFilter = document.getElementById('map-search-filter');
    const resetButton = document.getElementById('map-reset-filters');
    const summary = document.getElementById('map-visible-summary');
    const providerStatus = document.getElementById('map-provider-status');

    if (providerStatus) {
        providerStatus.textContent = 'Fond de carte: basemap local ProjetCITY';
    }

    const countries = [...new Set(pointLinks.map((link) => link.dataset.country).filter(Boolean))].sort();
    const regions = [...new Set(pointLinks.map((link) => link.dataset.region).filter(Boolean))].sort();

    countries.forEach((country) => {
        const option = document.createElement('option');
        option.value = country;
        option.textContent = country;
        countrySelect.appendChild(option);
    });

    regions.forEach((region) => {
        const option = document.createElement('option');
        option.value = region;
        option.textContent = region;
        regionSelect.appendChild(option);
    });

    function renderStaticMap() {
        const selectedCountry = countrySelect.value;
        const selectedRegion = regionSelect.value;
        const selectedTheme = themeSelect.value || 'population';
        const minPopulation = Number(populationFilter.value || 0);
        const searchTerm = (searchFilter.value || '').trim().toLowerCase();
        let visibleCount = 0;

        populationValue.textContent = formatMapNumber(minPopulation);

        pointLinks.forEach((link) => {
            const cityName = (link.dataset.cityName || '').toLowerCase();
            const population = Number(link.dataset.population || 0);
            const isVisible = (!selectedCountry || link.dataset.country === selectedCountry)
                && (!selectedRegion || link.dataset.region === selectedRegion)
                && population >= minPopulation
                && (!searchTerm || cityName.includes(searchTerm));

            link.classList.toggle('is-hidden', !isVisible);
            applyStaticMarkerStyle(link, selectedTheme);

            if (isVisible) {
                visibleCount += 1;
            }
        });

        if (summary) {
            summary.textContent = `${visibleCount} villes visibles. Couche active: ${selectedTheme}.`;
        }
    }

    [countrySelect, regionSelect, themeSelect, populationFilter, searchFilter].forEach((element) => {
        element.addEventListener('input', renderStaticMap);
        element.addEventListener('change', renderStaticMap);
    });

    resetButton.addEventListener('click', () => {
        countrySelect.value = '';
        regionSelect.value = '';
        themeSelect.value = 'population';
        populationFilter.value = '0';
        searchFilter.value = '';
        renderStaticMap();
    });

    renderStaticMap();
});