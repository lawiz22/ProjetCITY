(function () {
    'use strict';

    /* ── helpers ─────────────────────────────────────────────── */

    function fmt(value) {
        return new Intl.NumberFormat('fr-CA').format(value || 0);
    }

    function cityUrl(slug, annotationYear) {
        var qs = new URLSearchParams(window.location.search);
        var fwd = new URLSearchParams();
        ['country', 'region', 'period', 'search'].forEach(function (k) {
            var v = qs.get(k);
            if (v) fwd.set(k, v);
        });
        if (annotationYear) fwd.set('focus_annotation', annotationYear);
        var s = fwd.toString();
        return '/cities/' + slug + (s ? '?' + s : '');
    }

    var THEME_LABELS = {
        population: 'Population',
        growth: 'Croissance',
        decline: 'Déclin',
        peak: 'Pics',
        annotations: 'Annotations',
        climate: 'Climat',
        density: 'Densit\u00e9',
        timetravel: 'Voyage dans le temps'
    };

    /* ── marker style per theme ──────────────────────────────── */

    function markerStyle(pt, theme) {
        if (theme === 'growth') {
            var g = pt.latest_growth_pct || 0;
            var c = g >= 0 ? '#1f9d66' : '#b33951';
            return { radius: Math.max(8, Math.min(26, 10 + Math.abs(g) / 4)), color: c, fillColor: c };
        }
        if (theme === 'decline') {
            var dc = pt.decline_count || 0;
            var cd = dc > 0 ? '#b33951' : '#b8c0cc';
            return { radius: Math.max(8, Math.min(24, 8 + dc * 3)), color: cd, fillColor: cd };
        }
        if (theme === 'peak') {
            var pp = pt.peak_population || pt.population || 0;
            return { radius: Math.max(8, Math.min(28, 8 + pp / 500000)), color: '#264653', fillColor: '#264653' };
        }
        if (theme === 'annotations') {
            var ac = pt.annotation_count || 0;
            var ca = ac > 0 ? '#2ecc71' : '#b8c0cc';
            return { radius: Math.max(5, Math.min(14, 5 + ac)), color: ca, fillColor: ca };
        }
        if (theme === 'density') {
            var geo = pt.geography;
            if (!geo || geo.density == null) {
                return { radius: 8, color: '#b8c0cc', fillColor: '#b8c0cc' };
            }
            var d = geo.density;
            /* 5-step scale: <200 green, 200-1000 lime, 1000-3000 yellow, 3000-6000 orange, >6000 red */
            var dc;
            if (d < 200)       dc = '#22c55e';
            else if (d < 1000) dc = '#84cc16';
            else if (d < 3000) dc = '#f59e0b';
            else if (d < 6000) dc = '#ef6c00';
            else               dc = '#dc2626';
            return { radius: Math.max(8, Math.min(24, 8 + Math.log10(d + 1) * 4)), color: dc, fillColor: dc };
        }
        if (theme === 'climate') {
            var cl = pt.climate;
            if (!cl || cl.winter_temp == null) {
                return { radius: 8, color: '#b8c0cc', fillColor: '#b8c0cc' };
            }
            var w = cl.winter_temp;
            /* cold <= -5  => blue,  hot >= 10 => red,  in-between => gradient */
            var t = Math.max(0, Math.min(1, (w + 5) / 15));
            var cr = Math.round(50 + t * 200);
            var cb = Math.round(230 - t * 180);
            var cg = Math.round(80 + (0.5 - Math.abs(t - 0.5)) * 120);
            var cc = 'rgb(' + cr + ',' + cg + ',' + cb + ')';
            return { radius: 12, color: cc, fillColor: cc };
        }
        return { radius: pt.radius || 10, color: pt.city_color || '#2f6fed', fillColor: pt.city_color || '#2f6fed' };
    }

    /* ── popup HTML ──────────────────────────────────────────── */

    function popupHtml(pt, theme) {
        var growth = (pt.latest_growth_pct == null)
            ? 'n/a'
            : pt.latest_growth_pct + '% (' + pt.latest_growth_decade + ')';

        var annotBlock = '';
        /* Annotations mode uses spotlight panel below — no popup */

        /* Geography block */
        var geoBlock = '';
        if (pt.geography) {
            var g = pt.geography;
            var geoLines = '';
            if (g.density != null) geoLines += '<tr><td>Densit\u00e9</td><td>~' + fmt(g.density) + ' hab./km\u00b2</td></tr>';
            if (g.area_km2 != null) geoLines += '<tr><td>Superficie</td><td>~' + fmt(g.area_km2) + ' km\u00b2</td></tr>';
            if (g.altitude != null) geoLines += '<tr><td>Altitude</td><td>~' + g.altitude + ' m</td></tr>';
            if (g.river) geoLines += '<tr><td>Cours d\u0027eau</td><td>' + g.river + '</td></tr>';
            var geoTable = geoLines ? '<table class="map-geo-table">' + geoLines + '</table>' : '';
            var geoBullets = '';
            if (theme === 'density' && g.geo_bullets && g.geo_bullets.length) {
                geoBullets = '<ul class="map-geo-bullets">' +
                    g.geo_bullets.map(function (b) { return '<li>' + b + '</li>'; }).join('') +
                    '</ul>';
            }
            geoBlock = '<div class="map-popup-geo">' + geoTable + geoBullets + '</div>';
        }

        /* Climate block */
        var climateBlock = '';
        if (pt.climate) {
            var cl = pt.climate;
            var temps = '';
            if (cl.winter_temp != null) temps += '❄️ Hiver : ' + cl.winter_temp + '°C';
            if (cl.summer_temp != null) temps += (temps ? '  &middot;  ' : '') + '☀️ Été : ' + cl.summer_temp + '°C';
            var typeLine = cl.climate_type ? '<p class="map-climate-type">' + cl.climate_type + '</p>' : '';
            var bulletLines = '';
            if (theme === 'climate' && cl.climate_bullets && cl.climate_bullets.length) {
                bulletLines = '<ul class="map-climate-bullets">' +
                    cl.climate_bullets.map(function (b) { return '<li>' + b + '</li>'; }).join('') +
                    '</ul>';
            }
            climateBlock = '<div class="map-popup-climate">' +
                '<p>' + temps + '</p>' + typeLine + bulletLines + '</div>';
        }

        return '<div class="map-popup">' +
            '<h3>' + pt.city_name + '</h3>' +
            '<p>' + pt.country + ' &middot; ' + pt.region + '</p>' +
            '<p>Population: ' + fmt(pt.population) + ' en ' + pt.year + '</p>' +
            '<p>Pic: ' + (pt.peak_population ? fmt(pt.peak_population) + ' en ' + pt.peak_year : 'n/a') + '</p>' +
            '<p>Croissance: ' + growth + '</p>' +
            climateBlock +
            geoBlock +
            annotBlock +
            '<a href="' + cityUrl(pt.city_slug) + '">Ouvrir la fiche</a>' +
            '</div>';
    }

    /* ── filter logic ────────────────────────────────────────── */

    function applyFilters(points, ctrls) {
        var minPop = Number(ctrls.popRange.value) || 0;
        var search = (ctrls.search.value || '').trim().toLowerCase();
        if (ctrls.popLabel) ctrls.popLabel.textContent = fmt(minPop);

        var country = ctrls.countrySelect ? ctrls.countrySelect.value : '';
        var regions = ctrls.regionList ? getCheckedRegions(ctrls.regionList) : null;

        return points.filter(function (p) {
            if (p.population < minPop) return false;
            if (search && p.city_name.toLowerCase().indexOf(search) === -1) return false;
            if (country && p.country !== country) return false;
            if (regions && !regions.has(p.region)) return false;
            return true;
        });
    }

    function getCheckedRegions(regionList) {
        var set = new Set();
        regionList.querySelectorAll('input[type="checkbox"]:checked').forEach(function (cb) {
            set.add(cb.value);
        });
        return set;
    }

    function updateRegionLabel(toggle, regionList) {
        if (!toggle || !regionList) return;
        var total = regionList.querySelectorAll('input[type="checkbox"]').length;
        var checked = regionList.querySelectorAll('input[type="checkbox"]:checked').length;
        toggle.firstChild.textContent = (checked === total) ? 'Toutes les régions ' : checked + ' région' + (checked > 1 ? 's' : '') + ' ';
    }

    /* ── main init ───────────────────────────────────────────── */

    function initMap() {
        var container = document.getElementById('city-map');
        if (!container) return;

        /* Read points from the global set by the template */
        var points = window.__mapPoints;
        if (!points || !points.length) {
            container.textContent = 'Aucune donnée de carte disponible.';
            return;
        }

        /* Check Leaflet */
        if (typeof L === 'undefined') {
            container.textContent = 'Leaflet non chargé — vérifiez votre connexion.';
            return;
        }

        /* Grab controls */
        var ctrls = {
            themePills: document.querySelectorAll('.map-layer-pill'),
            activeTheme: 'population',
            popRange: document.getElementById('map-population-filter'),
            popLabel: document.getElementById('map-population-value'),
            search: document.getElementById('map-search-filter'),
            summary: document.getElementById('map-visible-summary'),
            status: document.getElementById('map-provider-status'),
            reset: document.getElementById('map-reset-filters'),
            countrySelect: document.getElementById('map-filter-country'),
            regionToggle: document.getElementById('map-region-toggle'),
            regionDropdown: document.getElementById('map-region-dropdown'),
            regionList: document.getElementById('map-region-list'),
            visibleCount: document.getElementById('map-visible-count')
        };
        /* Shim: ctrls.theme acts like a {value} accessor */
        ctrls.theme = { get value() { return ctrls.activeTheme; }, set value(v) { ctrls.activeTheme = v; } };

        /* Restore saved default view */
        var savedView = null;
        try { savedView = JSON.parse(localStorage.getItem('ccs-map-view')); } catch (e) {}
        var initLat = (savedView && savedView.lat != null) ? savedView.lat : 45.5;
        var initLng = (savedView && savedView.lng != null) ? savedView.lng : -96;
        var initZoom = (savedView && savedView.zoom != null) ? savedView.zoom : 4;

        /* Create the Leaflet map */
        var map = L.map(container, {
            scrollWheelZoom: true,
            zoomControl: true,
            minZoom: 3,
            maxZoom: 18
        }).setView([initLat, initLng], initZoom);

        /* ── Tile providers ──────────────────────────────────── */
        var TILE_PROVIDERS = {
            'carto-voyager': {
                url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
                options: { maxZoom: 19, subdomains: 'abcd', attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>' },
                label: 'CARTO Voyager'
            },
            'carto-positron': {
                url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
                options: { maxZoom: 19, subdomains: 'abcd', attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>' },
                label: 'CARTO Positron'
            },
            'carto-dark': {
                url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
                options: { maxZoom: 19, subdomains: 'abcd', attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>' },
                label: 'CARTO Dark Matter'
            },
            'osm': {
                url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                options: { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' },
                label: 'OpenStreetMap'
            },
            'esri-satellite': {
                url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                options: { maxZoom: 18, attribution: '&copy; Esri, Maxar, Earthstar Geographics' },
                label: 'Esri Satellite'
            },
            'esri-topo': {
                url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
                options: { maxZoom: 18, attribution: '&copy; Esri, HERE, Garmin, OpenStreetMap contributors' },
                label: 'Esri Topo'
            },
            'opentopomap': {
                url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
                options: { maxZoom: 17, attribution: '&copy; <a href="https://opentopomap.org/">OpenTopoMap</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' },
                label: 'OpenTopoMap'
            },
            'ohm-historical': {
                style: 'https://www.openhistoricalmap.org/map-styles/main/main.json',
                options: { attribution: '&copy; <a href="https://www.openhistoricalmap.org/">OpenHistoricalMap</a> contributors' },
                label: 'Historical Map (OHM)',
                maplibre: true
            }
        };

        var currentTileKey = (savedView && savedView.tile) || localStorage.getItem('ccs-map-tile') || 'carto-voyager';
        if (!TILE_PROVIDERS[currentTileKey]) currentTileKey = 'carto-voyager';
        var currentTileLayer = null;
        var currentMaplibreMap = null;
        var ohmMapReady = false;

        /* Convert a YYYY-MM-DD string to a decimal year (e.g. 1914.0) */
        function dateToDecimalYear(dateStr) {
            var parts = dateStr.split('-');
            var y = parseInt(parts[0], 10);
            var m = parseInt(parts[1] || '1', 10) - 1;
            var d = parseInt(parts[2] || '1', 10);
            var dt = new Date(y, m, d);
            var yearStart = new Date(y, 0, 1);
            var yearEnd   = new Date(y + 1, 0, 1);
            return y + (dt - yearStart) / (yearEnd - yearStart);
        }

        /* Store original (base) filters per layer id so they can be restored */
        var _ohmBaseFilters = {};

        /* Apply date filter to every layer of a MapLibre GL map
         * Uses MapLibre expression syntax (not legacy filters). */
        function applyOhmDateFilter(glMap, dateStr) {
            if (!glMap || !glMap.getStyle) return;
            var style;
            try { style = glMap.getStyle(); } catch(e) { return; }
            if (!style || !style.layers) return;
            var decYear = dateToDecimalYear(dateStr);

            style.layers.forEach(function(layer) {
                if (layer.type === 'background' || !layer.source) return;

                /* Capture original filter on first encounter */
                if (!(layer.id in _ohmBaseFilters)) {
                    _ohmBaseFilters[layer.id] = layer.filter ? JSON.parse(JSON.stringify(layer.filter)) : null;
                }
                var base = _ohmBaseFilters[layer.id];

                /* Date constraint using expression syntax */
                var startOk = ['any',
                    ['!', ['has', 'start_decdate']],
                    ['<=', ['get', 'start_decdate'], decYear]
                ];
                var endOk = ['any',
                    ['!', ['has', 'end_decdate']],
                    ['>=', ['get', 'end_decdate'], decYear]
                ];

                var combined;
                if (base) {
                    combined = ['all', base, startOk, endOk];
                } else {
                    combined = ['all', startOk, endOk];
                }

                try { glMap.setFilter(layer.id, combined); } catch(e) {
                    // Some layers (raster, hillshade) don't support filters – ignore
                }
            });
        }

        function setTileLayer(key, ohmDate) {
            var provider = TILE_PROVIDERS[key];
            if (!provider) return;
            if (currentTileLayer) map.removeLayer(currentTileLayer);
            currentMaplibreMap = null;
            ohmMapReady = false;
            _ohmBaseFilters = {};   /* reset base filters for new style */

            if (provider.maplibre && typeof L.maplibreGL === 'function') {
                /* Vector tile layer via MapLibre GL */
                currentTileLayer = L.maplibreGL({
                    style: provider.style,
                    attribution: provider.options.attribution
                }).addTo(map);
                var glMap = currentTileLayer.getMaplibreMap();
                currentMaplibreMap = glMap;

                function onOhmStyleReady() {
                    if (ohmMapReady) return;  /* guard against double-fire */
                    ohmMapReady = true;
                    applyOhmDateFilter(glMap, currentOhmDate);
                }

                /* Handle both cases: style already loaded, or not yet */
                if (glMap.isStyleLoaded && glMap.isStyleLoaded()) {
                    onOhmStyleReady();
                } else {
                    glMap.once('styledata', onOhmStyleReady);
                }
            } else if (provider.url) {
                currentTileLayer = L.tileLayer(provider.url, provider.options).addTo(map);
            }

            currentTileKey = key;
            localStorage.setItem('ccs-map-tile', key);
            if (ctrls.status) ctrls.status.textContent = 'Fond de carte: ' + provider.label;
        }

        var currentOhmDate = '2020-01-01';

        function updateOhmDate(year) {
            currentOhmDate = year + '-01-01';
            if (currentTileKey === 'ohm-historical' && currentMaplibreMap && ohmMapReady) {
                applyOhmDateFilter(currentMaplibreMap, currentOhmDate);
            }
        }

        /* Set initial tile layer */
        var tileSelect = document.getElementById('map-tile-select');
        if (tileSelect) tileSelect.value = currentTileKey;
        setTileLayer(currentTileKey);

        /* Tile select change handler */
        if (tileSelect) {
            tileSelect.addEventListener('change', function () {
                setTileLayer(this.value);
            });
        }

        /* Restore saved theme */
        var savedTheme = (savedView && savedView.theme) ? savedView.theme : null;
        if (savedTheme) {
            ctrls.activeTheme = savedTheme;
            ctrls.themePills.forEach(function (pill) {
                pill.classList.toggle('is-active', pill.getAttribute('data-theme') === savedTheme);
            });
        }

        /* ── Save default view button ────────────────────────── */
        var saveBtn = document.getElementById('map-save-default');
        if (saveBtn) {
            saveBtn.addEventListener('click', function () {
                var center = map.getCenter();
                var state = {
                    lat: Math.round(center.lat * 10000) / 10000,
                    lng: Math.round(center.lng * 10000) / 10000,
                    zoom: map.getZoom(),
                    tile: currentTileKey,
                    theme: ctrls.activeTheme || 'population'
                };
                localStorage.setItem('ccs-map-view', JSON.stringify(state));
                saveBtn.textContent = '✅';
                setTimeout(function () { saveBtn.textContent = '💾'; }, 1500);
            });
        }

        var markerLayer = L.layerGroup().addTo(map);
        var renderCalled = false;

        /* ── render markers ──────────────────────────────────── */

        function render() {
            var theme = ctrls.activeTheme || 'population';
            markerLayer.clearLayers();
            var visible = applyFilters(points, ctrls);
            var coords = [];

            visible.forEach(function (pt) {
                var s = markerStyle(pt, theme);
                var m = L.circleMarker([pt.lat, pt.lng], {
                    radius: s.radius,
                    color: s.color,
                    fillColor: s.fillColor,
                    fillOpacity: 0.42,
                    weight: 2
                });
                /* In annotations mode: no popup, just spotlight + store coords */
                if (theme === 'annotations') {
                    (function (slug, lat, lng) {
                        m.on('click', function () {
                            if (typeof loadSpotlight === 'function') loadSpotlight(slug, lat, lng);
                        });
                    })(pt.city_slug, pt.lat, pt.lng);
                } else {
                    m.bindPopup(function () { return popupHtml(pt, theme); });
                }
                m.addTo(markerLayer);
                coords.push([pt.lat, pt.lng]);
            });

            if (ctrls.summary) {
                ctrls.summary.textContent = visible.length + ' villes visibles. Couche active\u00a0: ' + (THEME_LABELS[theme] || theme) + '.';
            }
            if (ctrls.visibleCount) {
                ctrls.visibleCount.textContent = visible.length + ' villes';
            }

            /* Toggle density legend */
            var densityLegend = document.getElementById('density-legend');
            if (densityLegend) densityLegend.style.display = theme === 'density' ? '' : 'none';

            if (coords.length) {
                if (!renderCalled && !savedView) {
                    map.fitBounds(coords, { padding: [28, 28], maxZoom: 7 });
                }
            } else if (!renderCalled && !savedView) {
                map.setView([45.5, -96], 4);
            }
            renderCalled = true;
        }

        /* ── event wiring ────────────────────────────────────── */

        /* ── Time-travel state ───────────────────────────────── */
        var ttData = null;       // {years: [...], cities: {...}}
        var ttLoading = false;
        var ttActive = false;
        var ttPlayInterval = null;
        var ttMarkerLayer = L.layerGroup();   // separate layer for time-travel
        var ttPanel = document.getElementById('timetravel-panel');
        var ttSlider = document.getElementById('tt-slider');
        var ttYearDisplay = document.getElementById('tt-year-display');
        var ttCityCount = document.getElementById('tt-city-count');
        var ttMinYear = document.getElementById('tt-min-year');
        var ttMaxYear = document.getElementById('tt-max-year');
        var ttPlayBtn = document.getElementById('tt-play-btn');
        var ttSpeed = document.getElementById('tt-speed');

        function fetchTimeTravelData(cb) {
            if (ttData) return cb(ttData);
            if (ttLoading) return;
            ttLoading = true;
            if (ttYearDisplay) ttYearDisplay.textContent = 'Chargement…';
            fetch('/map/time-travel')
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    ttData = d;
                    ttLoading = false;
                    cb(d);
                })
                .catch(function () {
                    ttLoading = false;
                    if (ttYearDisplay) ttYearDisplay.textContent = 'Erreur';
                });
        }

        var ttPreviousTileKey = null;

        function enterTimeTravel() {
            ttActive = true;
            markerLayer.clearLayers();
            markerLayer.remove();
            ttMarkerLayer.addTo(map);
            if (ttPanel) ttPanel.style.display = '';

            // Auto-switch to OHM historical basemap
            ttPreviousTileKey = currentTileKey;
            if (currentTileKey !== 'ohm-historical') {
                setTileLayer('ohm-historical');
                if (tileSelect) tileSelect.value = 'ohm-historical';
            }

            var mp = document.querySelector('.map-panel-full');
            if (mp) mp.classList.add('timetravel-active');
            setTimeout(function(){ map.invalidateSize(); }, 50);

            // Hide reading strip & density legend
            var readingStrip = document.querySelector('.map-reading-strip');
            if (readingStrip) readingStrip.style.display = 'none';
            var densityLeg = document.getElementById('density-legend');
            if (densityLeg) densityLeg.style.display = 'none';

            fetchTimeTravelData(function (d) {
                if (!d.years.length) return;
                ttSlider.min = 0;
                ttSlider.max = d.years.length - 1;
                ttSlider.value = d.years.length - 1;
                ttMinYear.textContent = d.years[0];
                ttMaxYear.textContent = d.years[d.years.length - 1];
                renderTimeTravelYear(d.years[d.years.length - 1]);
            });
        }

        function exitTimeTravel() {
            ttActive = false;
            stopTTPlay();
            ttMarkerLayer.clearLayers();
            ttMarkerLayer.remove();
            markerLayer.addTo(map);
            if (ttPanel) ttPanel.style.display = 'none';
            if (ttDetailsRow) ttDetailsRow.style.display = 'none';

            // Restore previous basemap
            if (ttPreviousTileKey && ttPreviousTileKey !== 'ohm-historical') {
                setTileLayer(ttPreviousTileKey);
                if (tileSelect) tileSelect.value = ttPreviousTileKey;
            }
            ttPreviousTileKey = null;

            var mp = document.querySelector('.map-panel-full');
            if (mp) mp.classList.remove('timetravel-active');
            setTimeout(function(){ map.invalidateSize(); }, 50);

            // Restore reading strip
            var readingStrip = document.querySelector('.map-reading-strip');
            if (readingStrip) readingStrip.style.display = '';

            render();
        }

        function getPopulationForYear(cityData, targetYear) {
            // Find exact match or interpolate between nearest years
            var data = cityData.data;
            if (data[String(targetYear)] != null) return data[String(targetYear)];

            var years = Object.keys(data).map(Number).sort(function (a, b) { return a - b; });
            if (!years.length) return null;

            // If target is before first data point, no data
            if (targetYear < years[0]) return null;
            // If target is after last data point, no data
            if (targetYear > years[years.length - 1]) return null;

            // Interpolate between the two nearest years
            var lower = null, upper = null;
            for (var i = 0; i < years.length; i++) {
                if (years[i] <= targetYear) lower = years[i];
                if (years[i] >= targetYear && upper === null) upper = years[i];
            }
            if (lower === null || upper === null) return null;
            if (lower === upper) return data[String(lower)];

            var ratio = (targetYear - lower) / (upper - lower);
            var popLow = data[String(lower)];
            var popHigh = data[String(upper)];
            return Math.round(popLow + (popHigh - popLow) * ratio);
        }

        function renderTimeTravelYear(year) {
            if (!ttData) return;
            ttMarkerLayer.clearLayers();
            updateOhmDate(year);

            var cities = ttData.cities;
            var slugs = Object.keys(cities);
            var maxPop = 0;
            var pointsForYear = [];

            // First pass: compute populations and find max
            slugs.forEach(function (slug) {
                var city = cities[slug];
                var pop = getPopulationForYear(city, year);
                if (pop != null && pop > 0) {
                    pointsForYear.push({ slug: slug, city: city, pop: pop });
                    if (pop > maxPop) maxPop = pop;
                }
            });

            // Apply filters (country, region, search)
            var country = ctrls.countrySelect ? ctrls.countrySelect.value : '';
            var regions = ctrls.regionList ? getCheckedRegions(ctrls.regionList) : null;
            var search = (ctrls.search.value || '').trim().toLowerCase();

            pointsForYear = pointsForYear.filter(function (p) {
                if (country && p.city.country !== country) return false;
                if (regions && !regions.has(p.city.region)) return false;
                if (search && p.city.name.toLowerCase().indexOf(search) === -1) return false;
                return true;
            });

            // Second pass: draw markers
            pointsForYear.forEach(function (p) {
                var radius = maxPop > 0 ? Math.max(5, Math.min(32, 5 + (p.pop / maxPop) * 27)) : 8;
                var m = L.circleMarker([p.city.lat, p.city.lng], {
                    radius: radius,
                    color: p.city.color,
                    fillColor: p.city.color,
                    fillOpacity: 0.55,
                    weight: 2
                });
                m.bindPopup(
                    '<div class="map-popup">' +
                    '<h3>' + p.city.name + '</h3>' +
                    '<p>' + p.city.country + ' · ' + p.city.region + '</p>' +
                    '<p><strong>' + fmt(p.pop) + '</strong> habitants en <strong>' + year + '</strong></p>' +
                    '<a href="/cities/' + p.slug + '">Ouvrir la fiche</a>' +
                    '</div>'
                );
                m.addTo(ttMarkerLayer);
            });

            if (ttYearDisplay) ttYearDisplay.textContent = year;
            if (ttCityCount) ttCityCount.textContent = pointsForYear.length + ' villes';
            if (ctrls.summary) {
                ctrls.summary.textContent = pointsForYear.length + ' villes en ' + year + '. Couche active\u00a0: Voyage dans le temps.';
            }
            if (ctrls.visibleCount) {
                ctrls.visibleCount.textContent = pointsForYear.length + ' villes';
            }
            // Update block 1 count
            var ttBlock1Count = document.getElementById('tt-block1-count');
            if (ttBlock1Count) {
                ttBlock1Count.textContent = '\u2014 ' + pointsForYear.length + ' villes en ' + year;
            }

            updateTTDetails(pointsForYear, year);

            // Auto-zoom: fit map to visible cities
            var ttAutoZoom = document.getElementById('tt-autozoom');
            if (ttAutoZoom && ttAutoZoom.checked && pointsForYear.length) {
                var bounds = L.latLngBounds(pointsForYear.map(function (p) {
                    return [p.city.lat, p.city.lng];
                }));
                map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
            }
        }

        /* ── Time-travel detail panels ──────────────────────── */
        var ttDetailsRow = document.getElementById('tt-details-row');
        var ttCityTbody = document.getElementById('tt-city-tbody');
        var ttAnnotationsList = document.getElementById('tt-annotations-list');

        // Chroniques city filter
        var ttChronoFilterBtn = document.getElementById('tt-chrono-filter-btn');
        var ttChronoDropdown = document.getElementById('tt-chrono-dropdown');
        var ttChronoDropdownList = document.getElementById('tt-chrono-dropdown-list');
        var ttChronoAll = document.getElementById('tt-chrono-all');
        var ttChronoNone = document.getElementById('tt-chrono-none');
        var ttChronoChecked = null; // null = all checked (no filter active)
        var ttLastAnnotations = [];

        // Toggle dropdown
        if (ttChronoFilterBtn) {
            ttChronoFilterBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                var vis = ttChronoDropdown.style.display === 'none';
                ttChronoDropdown.style.display = vis ? '' : 'none';
            });
        }
        // Close dropdown on click outside
        document.addEventListener('click', function (e) {
            if (ttChronoDropdown && ttChronoDropdown.style.display !== 'none') {
                if (!ttChronoDropdown.contains(e.target) && e.target !== ttChronoFilterBtn) {
                    ttChronoDropdown.style.display = 'none';
                }
            }
        });
        // Tout / Aucun
        if (ttChronoAll) {
            ttChronoAll.addEventListener('click', function () {
                ttChronoChecked = null;
                var cbs = ttChronoDropdownList.querySelectorAll('input[type="checkbox"]');
                cbs.forEach(function (cb) { cb.checked = true; });
                ttChronoFilterBtn.classList.remove('is-filtered');
                renderChronoFiltered();
            });
        }
        if (ttChronoNone) {
            ttChronoNone.addEventListener('click', function () {
                ttChronoChecked = new Set();
                var cbs = ttChronoDropdownList.querySelectorAll('input[type="checkbox"]');
                cbs.forEach(function (cb) { cb.checked = false; });
                ttChronoFilterBtn.classList.add('is-filtered');
                renderChronoFiltered();
            });
        }

        function buildChronoChecklist(annotations) {
            if (!ttChronoDropdownList) return;
            var cities = [];
            annotations.forEach(function (a) {
                if (cities.indexOf(a.city) === -1) cities.push(a.city);
            });
            cities.sort(function (a, b) { return a.localeCompare(b); });

            var html = '';
            cities.forEach(function (city) {
                var checked = !ttChronoChecked || ttChronoChecked.has(city);
                html += '<label><input type="checkbox" value="' + city.replace(/"/g, '&quot;') + '"' +
                    (checked ? ' checked' : '') + '> ' + city + '</label>';
            });
            ttChronoDropdownList.innerHTML = html;

            // Listen for changes
            ttChronoDropdownList.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
                cb.addEventListener('change', function () {
                    // Build set from current checkboxes
                    var allCbs = ttChronoDropdownList.querySelectorAll('input[type="checkbox"]');
                    var allChecked = true;
                    var checked = new Set();
                    allCbs.forEach(function (c) {
                        if (c.checked) checked.add(c.value);
                        else allChecked = false;
                    });
                    ttChronoChecked = allChecked ? null : checked;
                    ttChronoFilterBtn.classList.toggle('is-filtered', !allChecked);
                    renderChronoFiltered();
                });
            });
        }

        function renderChronoFiltered() {
            if (!ttAnnotationsList) return;
            var filtered = ttLastAnnotations;
            if (ttChronoChecked) {
                filtered = ttLastAnnotations.filter(function (a) {
                    return ttChronoChecked.has(a.city);
                });
            }
            var aHtml = '';
            filtered.forEach(function (a) {
                aHtml += '<div class="tt-annotation-card">' +
                    '<div class="tt-annotation-header">' +
                    '<span class="tt-annotation-dot" style="background:' + a.color + '"></span>' +
                    '<strong><a href="/cities/' + a.slug + '">' + a.city + '</a></strong>' +
                    '<span class="tt-annotation-range">' + a.period.range + '</span>' +
                    '</div>' +
                    '<div class="tt-annotation-title">' + a.period.title + '</div>' +
                    '<div class="tt-annotation-summary">' + a.period.summary + '</div>' +
                    '</div>';
            });
            if (!filtered.length) {
                aHtml = '<p class="tt-no-data">Aucune chronique disponible pour cette sélection.</p>';
            }
            ttAnnotationsList.innerHTML = aHtml;
        }

        function updateTTDetails(pointsForYear, year) {
            if (!ttDetailsRow) return;
            ttDetailsRow.style.display = pointsForYear.length ? '' : 'none';

            // ── Block 1: City table ──
            if (ttCityTbody) {
                // Sort by population descending
                var sorted = pointsForYear.slice().sort(function (a, b) { return b.pop - a.pop; });
                var html = '';
                sorted.forEach(function (p) {
                    var density = '';
                    if (p.city.area && p.city.area > 0) {
                        density = Math.round(p.pop / p.city.area);
                        density = fmt(density) + '/km²';
                    } else if (p.city.density) {
                        density = fmt(Math.round(p.city.density)) + '/km²';
                    }
                    html += '<tr>' +
                        '<td><a href="/cities/' + p.slug + '">' + p.city.name + '</a></td>' +
                        '<td>' + p.city.region + '</td>' +
                        '<td class="num">' + fmt(p.pop) + '</td>' +
                        '<td class="num">' + density + '</td>' +
                        '<td class="num">' + year + '</td>' +
                        '</tr>';
                });
                ttCityTbody.innerHTML = html;
            }

            // ── Block 2: Period annotations ──
            if (ttAnnotationsList) {
                // Collect the active period for each visible city at this year
                var annotations = [];
                pointsForYear.forEach(function (p) {
                    if (!p.city.periods || !p.city.periods.length) return;
                    // Find the period that covers the current year
                    var activePeriod = null;
                    for (var i = 0; i < p.city.periods.length; i++) {
                        var pd = p.city.periods[i];
                        var start = pd.start || 0;
                        var end = pd.end || 9999;
                        if (year >= start && year <= end) {
                            activePeriod = pd;
                            break;
                        }
                    }
                    // Fallback: if year is after all periods, use the last one
                    if (!activePeriod) {
                        for (var j = p.city.periods.length - 1; j >= 0; j--) {
                            if (p.city.periods[j].start && year >= p.city.periods[j].start) {
                                activePeriod = p.city.periods[j];
                                break;
                            }
                        }
                    }
                    if (activePeriod) {
                        annotations.push({
                            city: p.city.name,
                            slug: p.slug,
                            color: p.city.color,
                            period: activePeriod
                        });
                    }
                });

                // Sort by city name
                annotations.sort(function (a, b) { return a.city.localeCompare(b.city); });

                ttLastAnnotations = annotations;
                buildChronoChecklist(annotations);
                renderChronoFiltered();
            }
        }

        // Slider input handler
        if (ttSlider) {
            ttSlider.addEventListener('input', function () {
                if (!ttData) return;
                var idx = Number(ttSlider.value);
                var year = ttData.years[idx];
                renderTimeTravelYear(year);
            });
        }

        // Play / Pause
        function stopTTPlay() {
            if (ttPlayInterval) {
                clearInterval(ttPlayInterval);
                ttPlayInterval = null;
            }
            if (ttPlayBtn) ttPlayBtn.textContent = '▶️ Lecture';
        }

        if (ttPlayBtn) {
            ttPlayBtn.addEventListener('click', function () {
                if (ttPlayInterval) {
                    stopTTPlay();
                    return;
                }
                if (!ttData || !ttData.years.length) return;
                ttPlayBtn.textContent = '⏸️ Pause';
                var speed = Number(ttSpeed.value) || 800;
                ttPlayInterval = setInterval(function () {
                    var idx = Number(ttSlider.value);
                    if (idx >= ttData.years.length - 1) {
                        ttSlider.value = 0;
                        idx = 0;
                    } else {
                        idx++;
                        ttSlider.value = idx;
                    }
                    renderTimeTravelYear(ttData.years[idx]);
                }, speed);
            });
        }

        if (ttSpeed) {
            ttSpeed.addEventListener('change', function () {
                if (ttPlayInterval) {
                    stopTTPlay();
                    ttPlayBtn.click();  // restart with new speed
                }
            });
        }

        // Navigation arrows: step by N years
        function ttStepYears(delta) {
            if (!ttData || !ttData.years.length) return;
            var curIdx = Number(ttSlider.value);
            var curYear = ttData.years[curIdx];
            var targetYear = curYear + delta;
            // Find the nearest index for targetYear
            var bestIdx = curIdx;
            var bestDist = Infinity;
            for (var i = 0; i < ttData.years.length; i++) {
                var d = Math.abs(ttData.years[i] - targetYear);
                if (d < bestDist) { bestDist = d; bestIdx = i; }
            }
            // Ensure we actually move at least 1 index in the right direction
            if (bestIdx === curIdx && delta > 0 && curIdx < ttData.years.length - 1) bestIdx = curIdx + 1;
            if (bestIdx === curIdx && delta < 0 && curIdx > 0) bestIdx = curIdx - 1;
            ttSlider.value = bestIdx;
            renderTimeTravelYear(ttData.years[bestIdx]);
        }

        ['tt-back10','tt-back1','tt-fwd1','tt-fwd10'].forEach(function (id) {
            var btn = document.getElementById(id);
            if (btn) btn.addEventListener('click', function () {
                var deltas = {'tt-back10': -10, 'tt-back1': -1, 'tt-fwd1': 1, 'tt-fwd10': 10};
                ttStepYears(deltas[id]);
            });
        });

        /* Layer pills */
        ctrls.themePills.forEach(function (pill) {
            pill.addEventListener('click', function () {
                ctrls.themePills.forEach(function (p) { p.classList.remove('is-active'); });
                pill.classList.add('is-active');
                var theme = pill.getAttribute('data-theme');
                ctrls.activeTheme = theme;

                /* Hide spotlight when leaving annotations */
                if (typeof hideSpotlight === 'function') hideSpotlight();

                if (theme === 'timetravel') {
                    enterTimeTravel();
                } else {
                    if (ttActive) exitTimeTravel();
                    else render();
                }
            });
        });

        [ctrls.popRange, ctrls.search].forEach(function (el) {
            if (el) {
                el.addEventListener('input', function () {
                    if (ttActive && ttData) {
                        var idx = Number(ttSlider.value);
                        renderTimeTravelYear(ttData.years[idx]);
                    } else { render(); }
                });
                el.addEventListener('change', function () {
                    if (ttActive && ttData) {
                        var idx = Number(ttSlider.value);
                        renderTimeTravelYear(ttData.years[idx]);
                    } else { render(); }
                });
            }
        });

        if (ctrls.reset) {
            ctrls.reset.addEventListener('click', function () {
                if (ttActive) exitTimeTravel();
                ctrls.activeTheme = 'population';
                ctrls.themePills.forEach(function (p) {
                    p.classList.toggle('is-active', p.getAttribute('data-theme') === 'population');
                });
                ctrls.popRange.value = '0';
                ctrls.search.value = '';
                if (ctrls.countrySelect) ctrls.countrySelect.value = '';
                if (ctrls.regionList) {
                    ctrls.regionList.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = true; });
                    updateRegionLabel(ctrls.regionToggle, ctrls.regionList);
                }
                render();
            });
        }

        /* Country / Region filters */
        function ttRerender() {
            if (ttActive && ttData) {
                var idx = Number(ttSlider.value);
                renderTimeTravelYear(ttData.years[idx]);
            } else { render(); }
        }
        if (ctrls.countrySelect) {
            ctrls.countrySelect.addEventListener('change', ttRerender);
        }
        if (ctrls.regionToggle && ctrls.regionDropdown) {
            ctrls.regionToggle.addEventListener('click', function (e) {
                e.stopPropagation();
                ctrls.regionDropdown.classList.toggle('is-open');
            });
            document.addEventListener('click', function (e) {
                if (!ctrls.regionDropdown.contains(e.target) && e.target !== ctrls.regionToggle) {
                    ctrls.regionDropdown.classList.remove('is-open');
                }
            });
        }
        if (ctrls.regionList) {
            ctrls.regionList.addEventListener('change', function () {
                updateRegionLabel(ctrls.regionToggle, ctrls.regionList);
                ttRerender();
            });
        }
        ctrls.regionDropdown && ctrls.regionDropdown.querySelectorAll('[data-region-action]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var check = btn.dataset.regionAction === 'all';
                ctrls.regionList.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = check; });
                updateRegionLabel(ctrls.regionToggle, ctrls.regionList);
                ttRerender();
            });
        });

        map.on('popupopen', function (e) {
            var el = e.popup.getElement();
            if (!el) return;
            el.querySelectorAll('.map-popup-annotation').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var slug = btn.getAttribute('data-slug');
                    var year = btn.getAttribute('data-year');
                    if (slug && year) window.location.href = cityUrl(slug, year);
                });
            });
            /* Spotlight button in annotations mode */
            el.querySelectorAll('.map-popup-spotlight-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var slug = btn.getAttribute('data-spotlight-slug');
                    if (slug) loadSpotlight(slug);
                });
            });
        });

        /* ── Annotation Spotlight ────────────────────────────── */
        var spotlightPanel = document.getElementById('spotlight-panel');
        var spotlightCache = {};
        var spotlightLat = null;
        var spotlightLng = null;

        function loadSpotlight(slug, lat, lng) {
            if (!spotlightPanel) return;
            spotlightLat = lat || null;
            spotlightLng = lng || null;
            spotlightPanel.style.display = '';
            var mp = document.querySelector('.map-panel-full');
            if (mp) mp.classList.add('spotlight-active');
            window.scrollTo({ top: 0, behavior: 'instant' });
            setTimeout(function(){ map.invalidateSize(); }, 50);
            var cityHeader = document.getElementById('spotlight-city-header');
            if (cityHeader) cityHeader.innerHTML = '<p class="spotlight-loading">Chargement…</p>';
            document.getElementById('spotlight-photos').innerHTML = '';
            document.getElementById('spotlight-fiche').innerHTML = '';
            document.getElementById('spotlight-annotations').innerHTML = '';
            document.getElementById('spotlight-periods').innerHTML = '';

            if (spotlightCache[slug]) {
                renderSpotlight(spotlightCache[slug]);
                return;
            }
            fetch('/map/city-spotlight/' + encodeURIComponent(slug))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.error) {
                        if (cityHeader) cityHeader.innerHTML = '<p>' + data.error + '</p>';
                        return;
                    }
                    spotlightCache[slug] = data;
                    renderSpotlight(data);
                })
                .catch(function () {
                    if (cityHeader) cityHeader.innerHTML = '<p>Erreur de chargement.</p>';
                });
        }

        function renderSpotlight(d) {
            /* ── City header ── */
            var heroImg = '';
            if (d.has_photo && d.photo_path) {
                heroImg = '<img class="spotlight-hero" src="/static/' + d.photo_path + '" alt="' + d.city_name + '">';
            }
            var trendClass = d.trend_label === 'En croissance' ? 'up' : (d.trend_label === 'En décroissance' ? 'down' : 'stable');
            var headerHtml = heroImg +
                '<div class="spotlight-city-info">' +
                '<h2>' + d.city_name + '</h2>' +
                '<p class="spotlight-sub">' + d.country + ' · ' + d.region + '</p>' +
                '<div class="spotlight-stats">' +
                '<div class="spotlight-stat"><span class="spotlight-stat-value">' + fmt(d.population) + '</span><span class="spotlight-stat-label">Population (' + d.year + ')</span></div>' +
                (d.peak_population ? '<div class="spotlight-stat"><span class="spotlight-stat-value">' + fmt(d.peak_population) + '</span><span class="spotlight-stat-label">Pic (' + d.peak_year + ')</span></div>' : '') +
                (d.first_population ? '<div class="spotlight-stat"><span class="spotlight-stat-value">' + fmt(d.first_population) + '</span><span class="spotlight-stat-label">Première donnée (' + d.first_population_year + ')</span></div>' : '') +
                '<div class="spotlight-stat"><span class="spotlight-stat-value spotlight-trend-' + trendClass + '">' + d.trend_symbol + ' ' + d.trend_label + '</span><span class="spotlight-stat-label">Tendance</span></div>' +
                '</div>' +
                '<div class="spotlight-actions">' +
                '<a href="' + d.detail_url + '" target="_blank" class="spotlight-action-btn spotlight-btn-fiche">📄 Ouvrir la fiche</a>' +
                '<button type="button" class="spotlight-action-btn spotlight-btn-zoom" id="spotlight-zoom-btn">🔍 Zoom rue</button>' +
                '</div>' +
                '</div>';
            document.getElementById('spotlight-city-header').innerHTML = headerHtml;

            /* Update topbar label */
            var topbarLabel = document.getElementById('spotlight-topbar-label');
            if (topbarLabel) topbarLabel.textContent = '📌 ' + d.city_name;

            /* Wire zoom button */
            var zoomBtn = document.getElementById('spotlight-zoom-btn');
            if (zoomBtn && spotlightLat != null && spotlightLng != null) {
                zoomBtn.addEventListener('click', function () {
                    map.setView([spotlightLat, spotlightLng], 16, { animate: true });
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                });
            }

            /* ── Photos ── */
            var photosEl = document.getElementById('spotlight-photos');
            if (d.photos && d.photos.length) {
                var photosHtml = '<h3>📷 Photos (' + d.photos.length + ')</h3><div class="spotlight-photo-grid">';
                d.photos.forEach(function (ph) {
                    photosHtml += '<div class="spotlight-photo-card"><img src="' + ph.url + '" alt="" loading="lazy"></div>';
                });
                photosHtml += '</div>';
                photosEl.innerHTML = photosHtml;
            }

            /* ── Fiche sections ── */
            var ficheEl = document.getElementById('spotlight-fiche');
            if (d.fiche_sections && d.fiche_sections.length) {
                var ficheHtml = '<h3>📋 Résumé de la fiche</h3><div class="spotlight-fiche-sections">';
                d.fiche_sections.forEach(function (s) {
                    ficheHtml += '<details class="spotlight-fiche-section"><summary>' + s.emoji + ' ' + s.title + '</summary>' +
                        '<div class="spotlight-fiche-content">' + s.html + '</div></details>';
                });
                ficheHtml += '</div>';
                ficheEl.innerHTML = ficheHtml;
            }

            /* ── Annotations ── */
            var annotEl = document.getElementById('spotlight-annotations');
            if (d.annotations && d.annotations.length) {
                var annotHtml = '<h3>📌 Annotations (' + d.annotations.length + ')</h3><div class="spotlight-annot-list">';
                d.annotations.forEach(function (a) {
                    annotHtml += '<div class="spotlight-annot-item">';
                    annotHtml += '<span class="spotlight-annot-dot" style="background:' + a.color + '"></span>';
                    annotHtml += '<span class="spotlight-annot-year">' + a.year + '</span>';
                    annotHtml += '<span class="spotlight-annot-label">' + a.label + '</span>';
                    if (a.photoUrl) {
                        annotHtml += '<img class="spotlight-annot-photo" src="' + a.photoUrl + '" alt="" loading="lazy">';
                    }
                    annotHtml += '</div>';
                });
                annotHtml += '</div>';
                annotEl.innerHTML = annotHtml;
            }

            /* ── Periods ── */
            var periodsEl = document.getElementById('spotlight-periods');
            if (d.periods && d.periods.length) {
                var periodsHtml = '<h3>📜 Périodes (' + d.periods.length + ')</h3><div class="spotlight-period-list">';
                d.periods.forEach(function (p) {
                    periodsHtml += '<div class="spotlight-period-card">';
                    periodsHtml += '<div class="spotlight-period-header"><strong>' + p.range + '</strong> — ' + p.title + '</div>';
                    if (p.start_pop || p.end_pop) {
                        periodsHtml += '<div class="spotlight-period-kpis">';
                        periodsHtml += '<span>Pop. ' + (p.start_pop ? fmt(p.start_pop) : '?') + ' → ' + (p.end_pop ? fmt(p.end_pop) : '?') + '</span>';
                        if (p.change_pct != null) periodsHtml += '<span> (' + p.change_pct + '%)</span>';
                        periodsHtml += '</div>';
                    }
                    if (p.summary) {
                        periodsHtml += '<p class="spotlight-period-summary">' + p.summary + '</p>';
                    }
                    if (p.annotations && p.annotations.length) {
                        periodsHtml += '<div class="spotlight-period-annotations">';
                        p.annotations.forEach(function (a) {
                            periodsHtml += '<span class="spotlight-period-ann-chip" style="border-left: 3px solid ' + a.color + '">';
                            if (a.photoUrl) periodsHtml += '<img src="' + a.photoUrl + '" alt="" loading="lazy">';
                            periodsHtml += a.year + ' · ' + a.label + '</span>';
                        });
                        periodsHtml += '</div>';
                    }
                    periodsHtml += '</div>';
                });
                periodsHtml += '</div>';
                periodsEl.innerHTML = periodsHtml;
            }
        }

        /* Also trigger spotlight when clicking a marker in annotations mode */
        map.on('click', function () {
            /* Close spotlight if clicking empty map area */
        });

        /* Hide spotlight when switching away from annotations pill */
        var mapPanel = document.querySelector('.map-panel-full');
        function hideSpotlight() {
            if (spotlightPanel) spotlightPanel.style.display = 'none';
            if (mapPanel) mapPanel.classList.remove('spotlight-active');
            setTimeout(function(){ map.invalidateSize(); }, 50);
        }

        /* Close button */
        var spotlightCloseBtn = document.getElementById('spotlight-close-btn');
        if (spotlightCloseBtn) {
            spotlightCloseBtn.addEventListener('click', hideSpotlight);
        }

        /* ── refresh button (AJAX reload) ────────────────────── */

        var refreshBtn = document.getElementById('map-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', function () {
                refreshBtn.disabled = true;
                refreshBtn.classList.add('is-loading');
                fetch('/map/data')
                    .then(function (r) { return r.json(); })
                    .then(function (newPoints) {
                        points = newPoints;
                        window.__mapPoints = newPoints;
                        var _origFitBounds = map.fitBounds;
                        var _origSetView = map.setView;
                        map.fitBounds = function () { return map; };
                        map.setView = function () { return map; };
                        render();
                        map.fitBounds = _origFitBounds;
                        map.setView = _origSetView;
                    })
                    .catch(function () {})
                    .then(function () {
                        refreshBtn.disabled = false;
                        refreshBtn.classList.remove('is-loading');
                    });
            });
        }

        /* ── Geocode missing cities button ───────────────── */
        var geocodeBtn = document.getElementById('map-geocode-btn');
        if (geocodeBtn) {
            geocodeBtn.addEventListener('click', function () {
                geocodeBtn.disabled = true;
                geocodeBtn.textContent = '⏳ Géocodage…';
                fetch('/map/geocode-missing', { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        var msg = data.geocoded + '/' + data.total + ' ville(s) géocodée(s).';
                        if (data.geocoded > 0) {
                            geocodeBtn.textContent = '✅ ' + msg;
                            setTimeout(function () { window.location.reload(); }, 1500);
                        } else {
                            geocodeBtn.textContent = '⚠️ ' + msg;
                        }
                    })
                    .catch(function () {
                        geocodeBtn.textContent = '❌ Erreur';
                    });
            });
        }

        /* ── focus on city from URL param (?focus=slug) ──── */
        var urlParams = new URLSearchParams(window.location.search);
        var focusSlug = urlParams.get('focus');
        if (focusSlug) {
            var focusPt = null;
            for (var i = 0; i < points.length; i++) {
                if (points[i].city_slug === focusSlug) { focusPt = points[i]; break; }
            }
            if (focusPt) {
                savedView = null;           // override saved view
                renderCalled = false;       // allow fitBounds
                map.setView([focusPt.lat, focusPt.lng], 12);
                renderCalled = true;        // prevent render() from resetting
            }
        }

        /* ── auto-enter time-travel from URL (?tt=1&year=1900&country=Canada&region=Alberta) ── */
        if (urlParams.get('tt') === '1') {
            var ttUrlYear = Number(urlParams.get('year')) || null;
            var ttUrlCountry = urlParams.get('country') || '';
            var ttUrlRegion = urlParams.get('region') || '';

            // Pre-set country filter
            if (ttUrlCountry && ctrls.countrySelect) {
                ctrls.countrySelect.value = ttUrlCountry;
            }
            // Pre-set region filter: uncheck all, check only the target
            if (ttUrlRegion && ctrls.regionList) {
                ctrls.regionList.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
                    cb.checked = (cb.value === ttUrlRegion);
                });
                updateRegionLabel(ctrls.regionToggle, ctrls.regionList);
            }

            // Activate time-travel pill
            ctrls.themePills.forEach(function (p) { p.classList.remove('is-active'); });
            var ttPill = document.querySelector('[data-theme="timetravel"]');
            if (ttPill) ttPill.classList.add('is-active');

            // Enter time-travel and jump to requested year
            ttActive = true;
            markerLayer.clearLayers();
            markerLayer.remove();
            ttMarkerLayer.addTo(map);
            if (ttPanel) ttPanel.style.display = '';

            fetchTimeTravelData(function (d) {
                if (!d.years.length) return;
                ttSlider.min = 0;
                ttSlider.max = d.years.length - 1;
                ttMinYear.textContent = d.years[0];
                ttMaxYear.textContent = d.years[d.years.length - 1];

                // Find closest year index
                var targetIdx = d.years.length - 1;
                if (ttUrlYear) {
                    var bestDist = Infinity;
                    for (var i = 0; i < d.years.length; i++) {
                        var dist = Math.abs(d.years[i] - ttUrlYear);
                        if (dist < bestDist) { bestDist = dist; targetIdx = i; }
                    }
                }
                ttSlider.value = targetIdx;
                renderTimeTravelYear(d.years[targetIdx]);

                // Zoom to fit visible markers
                var bounds = [];
                ttMarkerLayer.eachLayer(function (layer) {
                    if (layer.getLatLng) bounds.push(layer.getLatLng());
                });
                if (bounds.length) {
                    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 });
                }
            });
        }

        /* ── zoom on search match ───────────────────────────── */
        if (ctrls.search) {
            ctrls.search.addEventListener('input', function () {
                var q = (ctrls.search.value || '').trim().toLowerCase();
                if (q.length < 2) return;
                var matches = points.filter(function (p) {
                    return p.city_name.toLowerCase().indexOf(q) !== -1;
                });
                if (matches.length === 1) {
                    map.setView([matches[0].lat, matches[0].lng], 10);
                } else if (matches.length > 1 && matches.length <= 10) {
                    var bounds = matches.map(function (p) { return [p.lat, p.lng]; });
                    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 10 });
                }
            });
        }

        /* ── first render ────────────────────────────────────── */

        render();

        /* Open popup for focused city after render */
        if (focusSlug) {
            markerLayer.eachLayer(function (layer) {
                if (layer.getLatLng) {
                    var ll = layer.getLatLng();
                    for (var j = 0; j < points.length; j++) {
                        if (points[j].city_slug === focusSlug &&
                            Math.abs(points[j].lat - ll.lat) < 0.0001 &&
                            Math.abs(points[j].lng - ll.lng) < 0.0001) {
                            layer.openPopup();
                            break;
                        }
                    }
                }
            });
        }

        /* Ensure Leaflet knows the container size */
        map.invalidateSize();
        setTimeout(function () { map.invalidateSize(); }, 100);
        setTimeout(function () { map.invalidateSize(); }, 500);
        setTimeout(function () { map.invalidateSize(); }, 1500);
        window.addEventListener('resize', function () { map.invalidateSize(); });
        window.addEventListener('load', function () { map.invalidateSize(); });
    }

    /* ── boot ────────────────────────────────────────────────── */

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMap);
    } else {
        initMap();
    }
})();