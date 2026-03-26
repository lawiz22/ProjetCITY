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
        density: 'Densit\u00e9'
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
            var ca = ac > 0 ? '#ef6c3d' : '#b8c0cc';
            return { radius: Math.max(8, Math.min(24, 8 + ac * 2)), color: ca, fillColor: ca };
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

        var annotations = pt.annotations || [];
        var annotBlock = '';
        if (theme === 'annotations') {
            if (annotations.length) {
                annotBlock = '<div class="map-popup-annotations">' +
                    annotations.map(function (a) {
                        return '<button type="button" class="map-popup-annotation" data-slug="' +
                            pt.city_slug + '" data-year="' + a.year + '">' +
                            '<span style="background:' + a.color + '"></span>' +
                            a.year + ' &middot; ' + a.label + '</button>';
                    }).join('') +
                    '</div>';
            } else {
                annotBlock = '<p>Aucune annotation.</p>';
            }
            annotBlock = '<div class="map-popup-layer"><strong>Annotations</strong>' + annotBlock + '</div>';
        }

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

        /* Create the Leaflet map */
        var map = L.map(container, {
            scrollWheelZoom: true,
            zoomControl: true,
            minZoom: 3,
            maxZoom: 18
        }).setView([45.5, -96], 4);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
            subdomains: 'abcd',
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
        }).addTo(map);

        if (ctrls.status) ctrls.status.textContent = 'Fond de carte: CARTO Voyager';

        var markerLayer = L.layerGroup().addTo(map);

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
                m.bindPopup(function () { return popupHtml(pt, theme); });
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
                map.fitBounds(coords, { padding: [28, 28], maxZoom: 7 });
            } else {
                map.setView([45.5, -96], 4);
            }
        }

        /* ── event wiring ────────────────────────────────────── */

        /* Layer pills */
        ctrls.themePills.forEach(function (pill) {
            pill.addEventListener('click', function () {
                ctrls.themePills.forEach(function (p) { p.classList.remove('is-active'); });
                pill.classList.add('is-active');
                ctrls.activeTheme = pill.getAttribute('data-theme');
                render();
            });
        });

        [ctrls.popRange, ctrls.search].forEach(function (el) {
            if (el) {
                el.addEventListener('input', render);
                el.addEventListener('change', render);
            }
        });

        if (ctrls.reset) {
            ctrls.reset.addEventListener('click', function () {
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
        if (ctrls.countrySelect) {
            ctrls.countrySelect.addEventListener('change', render);
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
                render();
            });
        }
        ctrls.regionDropdown && ctrls.regionDropdown.querySelectorAll('[data-region-action]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var check = btn.dataset.regionAction === 'all';
                ctrls.regionList.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = check; });
                updateRegionLabel(ctrls.regionToggle, ctrls.regionList);
                render();
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
        });

        /* ── first render ────────────────────────────────────── */

        render();

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