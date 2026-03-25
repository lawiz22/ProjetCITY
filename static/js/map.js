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
        annotations: 'Annotations'
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

        return '<div class="map-popup">' +
            '<h3>' + pt.city_name + '</h3>' +
            '<p>' + pt.country + ' &middot; ' + pt.region + '</p>' +
            '<p>Population: ' + fmt(pt.population) + ' en ' + pt.year + '</p>' +
            '<p>Pic: ' + (pt.peak_population ? fmt(pt.peak_population) + ' en ' + pt.peak_year : 'n/a') + '</p>' +
            '<p>Croissance: ' + growth + '</p>' +
            annotBlock +
            '<a href="' + cityUrl(pt.city_slug) + '">Ouvrir la fiche</a>' +
            '</div>';
    }

    /* ── filter logic ────────────────────────────────────────── */

    function applyFilters(points, ctrls) {
        var minPop = Number(ctrls.popRange.value) || 0;
        var search = (ctrls.search.value || '').trim().toLowerCase();
        if (ctrls.popLabel) ctrls.popLabel.textContent = fmt(minPop);

        return points.filter(function (p) {
            if (p.population < minPop) return false;
            if (search && p.city_name.toLowerCase().indexOf(search) === -1) return false;
            return true;
        });
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
            reset: document.getElementById('map-reset-filters')
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
                render();
            });
        }

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