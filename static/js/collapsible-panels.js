/*
 * Auto-collapse enhancement for .panel blocks on detail pages only.
 * - Activates only when <body> has class "detail-page".
 * - Prepends a ▾ chevron INSIDE the first <h2> of each panel so the title stays
 *   left-aligned inside the existing .panel-head layout.
 * - Ensures every panel h2 starts with an icon (keyword-based fallback → 📄).
 * - Persists per-panel state in localStorage keyed by pathname + panel key.
 * - Exposes window.toggleAllPanels(open?) for the global toolbar button.
 *
 * Opt out per-panel via class="no-collapse".
 */
(function () {
    'use strict';

    function isDetailPage() {
        return document.body && document.body.classList.contains('detail-page');
    }

    var STORAGE_PREFIX = 'projetcity-panel:';
    var ICON_MAP = [
        [/(courbe|graphe|graph|chart|évolution|croissance|nombre de)/i, '📈'],
        [/(configuration|réglage|paramètre|options|settings)/i, '⚙️'],
        [/(ajout|ajouter|nouveau|créer|nouvelle)/i, '➕'],
        [/(photo|image|galerie|album|bibliothèque)/i, '📷'],
        [/(recherche|search|suggérer|suggestion)/i, '🔍'],
        [/(fiche|résumé|description)/i, '📋'],
        [/(période|histoire|historique|timeline|chronolog)/i, '📜'],
        [/(annotation|repère|marqueur)/i, '🏷️'],
        [/(carte|map|géo)/i, '🗺️'],
        [/(source|référence|données)/i, '📊'],
        [/(fusion|merge|combin)/i, '🔀'],
        [/(légende|monument|événement|personnage)/i, '📖'],
        [/(sql|requête|query)/i, '💾'],
        [/(couverture|coverage)/i, '📐'],
        [/(admin|utilisateur|log|audit)/i, '🛠️'],
    ];
    var LEADING_EMOJI = /^\s*([\p{Extended_Pictographic}\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]|[✅⚠️❗✔️✖️✳️✴️❇️❌⭐🌟])\s*/u;

    function pathKey() {
        try { return window.location.pathname || '/'; } catch (e) { return '/'; }
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
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }

    function writeStored(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* ignore */ }
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
            if (LEADING_EMOJI.test(raw)) return;
        } catch (e) {
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

        // Body = everything inside the panel after .panel-head.
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

        // Arrow lives INSIDE the h2 so the title cluster stays left-aligned
        // inside the existing .panel-head layout (justify-content: space-between).
        var arrow = document.createElement('span');
        arrow.className = 'panel-collapse-arrow';
        arrow.setAttribute('aria-hidden', 'true');
        arrow.textContent = '▾';
        h2.insertBefore(arrow, h2.firstChild);

        head.classList.add('panel-collapse-head');
        head.setAttribute('aria-expanded', 'true');
        // Only the title cluster (first child of .panel-head) is the toggle
        // target so action buttons/forms living in the head stay clickable
        // and don't accidentally collapse the panel.
        var toggleZone = head.firstElementChild || head;
        toggleZone.classList.add('panel-collapse-toggle-zone');
        toggleZone.setAttribute('role', 'button');
        toggleZone.setAttribute('tabindex', '0');

        panel.dataset.collapseReady = '1';
        panel.dataset.collapseKey = keyFor(panel, index);

        var stored = readStored(panel.dataset.collapseKey);
        if (stored === '1') collapse(panel, true);

        function toggle(ev) {
            var target = ev.target;
            while (target && target !== toggleZone) {
                if (target.matches && target.matches('button, a, input, select, textarea, label')) {
                    return;
                }
                target = target.parentNode;
            }
            var wasCollapsed = panel.classList.contains('panel-collapsed');
            var nextState = !wasCollapsed;
            collapse(panel, nextState);
            writeStored(panel.dataset.collapseKey, nextState ? '1' : '0');
        }

        toggleZone.addEventListener('click', toggle);
        toggleZone.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                toggle(ev);
            }
        });
    }

    function enhanceAll() {
        document.querySelectorAll('.panel').forEach(function (panel, idx) {
            enhancePanel(panel, idx);
        });
    }

    window.toggleAllPanels = function (open) {
        var panels = document.querySelectorAll('.panel[data-collapse-ready="1"]');
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
        btn.addEventListener('click', function () { window.toggleAllPanels(); });
        var anyOpen = false;
        document.querySelectorAll('.panel[data-collapse-ready="1"]').forEach(function (p) {
            if (!p.classList.contains('panel-collapsed')) anyOpen = true;
        });
        btn.textContent = anyOpen ? '▾ Tout fermer' : '▸ Tout ouvrir';
    }

    function boot() {
        if (!isDetailPage()) return;
        enhanceAll();
        initGlobalButton();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
