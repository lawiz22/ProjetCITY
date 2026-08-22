/*
 * Auto-collapse enhancement for all <section class="panel"> blocks.
 * - Prepends a chevron ▾ to the .panel-head so the whole header is a toggle.
 * - Ensures every panel has an icon at the start of its <h2> (falls back to a
 *   keyword-based emoji, then to 📄) so collapsed panels stay scannable.
 * - Persists per-panel state in localStorage keyed by pathname + panel key.
 * - Exposes window.toggleAllPanels(open?) used by the global toolbar button.
 *
 * Opt out by adding class="no-collapse" on the <section> element.
 */
(function () {
    'use strict';

    var STORAGE_PREFIX = 'projetcity-panel:';
    var ICON_MAP = [
        [/(courbe|graphe|graph|chart|évolution|croissance|nombre de)/i, '📈'],
        [/(configuration|réglage|paramètre|options|settings)/i, '⚙️'],
        [/(ajout|ajouter|nouveau|créer|nouvelle)/i, '➕'],
        [/(photo|image|galerie|album|bibliothèque)/i, '📷'],
        [/(recherche|search|suggérer|suggestion)/i, '🔍'],
        [/(fiche|résumé|description)/i, '📋'],
        [/(période|histoire|historique|timeline|chronolog|évolution)/i, '📜'],
        [/(annotation|repère|marqueur)/i, '🏷️'],
        [/(carte|map|géo)/i, '🗺️'],
        [/(source|référence|données)/i, '📊'],
        [/(fusion|merge|combin)/i, '🔀'],
        [/(légende|monument|événement|personnage)/i, '📖'],
        [/(sql|requête|query)/i, '💾'],
        [/(couverture|coverage)/i, '📐'],
        [/(admin|utilisateur|log|audit)/i, '🛠️'],
    ];
    // Simple regex covering common emoji ranges + common pictographs so we can
    // detect whether an h2 already starts with a visual icon.
    var LEADING_EMOJI = /^\s*([\p{Extended_Pictographic}\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]|[✅⚠️❗✔️✖️✳️✴️❇️❌⭐🌟])\s*/u;

    function pathKey() {
        try {
            return window.location.pathname || '/';
        } catch (e) {
            return '/';
        }
    }

    function keyFor(panel, index) {
        var id = panel.id || '';
        if (!id) {
            var h = panel.querySelector('.panel-head h2, .panel-head h1');
            id = 'p' + index + '-' + (h ? (h.textContent || '').trim().slice(0, 60) : 'untitled');
        }
        return STORAGE_PREFIX + pathKey() + '::' + id;
    }

    function readStored(key) {
        try {
            return localStorage.getItem(key);
        } catch (e) {
            return null;
        }
    }

    function writeStored(key, value) {
        try {
            localStorage.setItem(key, value);
        } catch (e) { /* quota / privacy mode — ignore */ }
    }

    function pickIcon(text) {
        for (var i = 0; i < ICON_MAP.length; i++) {
            if (ICON_MAP[i][0].test(text)) return ICON_MAP[i][1];
        }
        return '📄';
    }

    function ensureIcon(h2) {
        var raw = (h2.textContent || '').trim();
        if (!raw) return;
        try {
            if (LEADING_EMOJI.test(raw)) return; // already has an icon
        } catch (e) {
            // Older engines lacking \p{Extended_Pictographic}: fall back to a
            // best-effort check for a non-ASCII leading char.
            if (/^\s*[^\x00-\x7F]/.test(raw)) return;
        }
        var icon = pickIcon(raw);
        var span = document.createElement('span');
        span.className = 'panel-auto-icon';
        span.setAttribute('aria-hidden', 'true');
        span.textContent = icon + ' ';
        h2.insertBefore(span, h2.firstChild);
    }

    function collapse(panel, collapsed) {
        panel.classList.toggle('panel-collapsed', collapsed);
        var arrow = panel.querySelector('.panel-collapse-arrow');
        if (arrow) arrow.textContent = collapsed ? '▸' : '▾';
        var head = panel.querySelector('.panel-head');
        if (head) head.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }

    function enhancePanel(panel, index) {
        if (panel.classList.contains('no-collapse')) return;
        if (panel.dataset.collapseReady === '1') return;
        var head = panel.querySelector(':scope > .panel-head');
        if (!head) return;
        var h2 = head.querySelector('h2, h1');
        if (!h2) return;

        // Body = everything after .panel-head (children of the panel).
        var body = document.createElement('div');
        body.className = 'panel-collapse-body';
        var next = head.nextSibling;
        while (next) {
            var toMove = next;
            next = next.nextSibling;
            body.appendChild(toMove);
        }
        panel.appendChild(body);

        ensureIcon(h2);

        var arrow = document.createElement('span');
        arrow.className = 'panel-collapse-arrow';
        arrow.setAttribute('aria-hidden', 'true');
        arrow.textContent = '▾';
        head.insertBefore(arrow, head.firstChild);

        head.classList.add('panel-collapse-head');
        head.setAttribute('role', 'button');
        head.setAttribute('tabindex', '0');
        head.setAttribute('aria-expanded', 'true');

        panel.dataset.collapseReady = '1';
        panel.dataset.collapseKey = keyFor(panel, index);

        var stored = readStored(panel.dataset.collapseKey);
        if (stored === '1') collapse(panel, true);

        function toggle(ev) {
            // Don't toggle when clicking on interactive controls inside the head
            // (buttons, links, form fields).
            var target = ev.target;
            while (target && target !== head) {
                if (target.matches && target.matches('button, a, input, select, textarea, label')) {
                    return;
                }
                target = target.parentNode;
            }
            var wasCollapsed = panel.classList.contains('panel-collapsed');
            var next = !wasCollapsed;
            collapse(panel, next);
            writeStored(panel.dataset.collapseKey, next ? '1' : '0');
        }

        head.addEventListener('click', toggle);
        head.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                toggle(ev);
            }
        });
    }

    function enhanceAll() {
        var panels = document.querySelectorAll('.panel');
        panels.forEach(function (panel, idx) {
            enhancePanel(panel, idx);
        });
    }

    window.toggleAllPanels = function (open) {
        var panels = document.querySelectorAll('.panel[data-collapse-ready="1"]');
        // If no explicit direction, pick based on whether any panel is open.
        if (typeof open !== 'boolean') {
            var anyOpen = false;
            panels.forEach(function (p) { if (!p.classList.contains('panel-collapsed')) anyOpen = true; });
            open = !anyOpen;
        }
        panels.forEach(function (p) {
            collapse(p, !open);
            if (p.dataset.collapseKey) writeStored(p.dataset.collapseKey, open ? '0' : '1');
        });
        var btn = document.getElementById('global-toggle-panels-btn');
        if (btn) btn.textContent = open ? '▾ Tout fermer' : '▸ Tout ouvrir';
    };

    function initGlobalButton() {
        var btn = document.getElementById('global-toggle-panels-btn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            window.toggleAllPanels();
        });
        // Initial label reflects current state.
        var anyOpen = false;
        document.querySelectorAll('.panel[data-collapse-ready="1"]').forEach(function (p) {
            if (!p.classList.contains('panel-collapsed')) anyOpen = true;
        });
        btn.textContent = anyOpen ? '▾ Tout fermer' : '▸ Tout ouvrir';
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            enhanceAll();
            initGlobalButton();
        });
    } else {
        enhanceAll();
        initGlobalButton();
    }
})();
