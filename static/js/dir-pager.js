/**
 * Shared client-side pagination module.
 *
 * Usage:
 *   var pager = initDirPager({
 *       prefix:       'evt',          // builds IDs: evt-pager-top, evt-pager-bottom, evt-per-page-select
 *       containerId:  'evt-dir-grid', // container element ID
 *       itemSelector: '.event-card',  // CSS selector for items inside container
 *       countElId:    'evt-dir-count',// counter element ID
 *       countSuffix:  'événement',    // singular label (plural = + 's' unless countSuffixPlural given)
 *       mirrorClass:  'evt-per-page-mirror' // class on bottom pager select mirrors
 *   });
 *
 *   // After filtering/sorting, pass the new array of DOM elements:
 *   pager.setItems(sortedArray);
 *
 *   // To reset page (e.g. after filter change):
 *   pager.resetPage();
 *
 *   // Access all original items:
 *   pager.getAllItems();
 */
function initDirPager(cfg) {
    var prefix = cfg.prefix;
    var container = document.getElementById(cfg.containerId);
    var countEl = document.getElementById(cfg.countElId);
    var perPageSelect = document.getElementById(prefix + '-per-page-select');
    var pagerTop = document.getElementById(prefix + '-pager-top');
    var pagerBottom = document.getElementById(prefix + '-pager-bottom');
    if (!container || !perPageSelect) return null;

    var mirrorClass = cfg.mirrorClass || (prefix + '-per-page-mirror');
    var mirrors = document.querySelectorAll('.' + mirrorClass);
    var countSuffix = cfg.countSuffix || 'élément';
    var countSuffixPlural = cfg.countSuffixPlural || (countSuffix + 's');
    var scrollTarget = cfg.scrollTarget ? document.getElementById(cfg.scrollTarget) : container;

    var allItems = Array.prototype.slice.call(container.querySelectorAll(cfg.itemSelector));
    var displayItems = allItems.slice();
    var currentPage = 1;

    /* ---- Helpers ---- */
    function getPerPage() {
        var v = perPageSelect.value;
        return v === 'all' ? (displayItems.length || 1) : parseInt(v, 10);
    }

    function totalPages() {
        return Math.max(1, Math.ceil(displayItems.length / getPerPage()));
    }

    /* ---- Render ---- */
    function render() {
        var pp = getPerPage();
        var total = totalPages();
        if (currentPage > total) currentPage = total;
        var start = (currentPage - 1) * pp;
        var end = start + pp;

        allItems.forEach(function(el) { el.style.display = 'none'; });
        displayItems.slice(start, end).forEach(function(el) { el.style.display = ''; });
        displayItems.forEach(function(el) { container.appendChild(el); });

        // Sync mirrors
        mirrors.forEach(function(m) { m.value = perPageSelect.value; });

        // Counter
        if (countEl) {
            var n = displayItems.length;
            countEl.textContent = n + ' ' + (n !== 1 ? countSuffixPlural : countSuffix);
        }

        // Pager info & arrows
        var infoText = 'Page ' + currentPage + ' de ' + total;
        var isFirst = currentPage <= 1;
        var isLast = currentPage >= total;
        var showNav = total > 1;

        [pagerTop, pagerBottom].forEach(function(pager) {
            if (!pager) return;
            // Always keep the per-page select visible; only hide arrows+info
            var right = pager.querySelector('.dir-pager-right');
            if (right) right.style.display = showNav ? '' : 'none';

            pager.querySelectorAll('.dir-pager-info').forEach(function(el) {
                el.textContent = infoText;
            });
            pager.querySelectorAll('.dir-pager-arrow').forEach(function(btn) {
                var d = btn.dataset.dir;
                btn.disabled = (d === 'first' || d === 'prev') ? isFirst : isLast;
            });
        });
    }

    /* ---- Arrow click handlers ---- */
    function bindArrows(pager) {
        if (!pager) return;
        pager.querySelectorAll('.dir-pager-arrow').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var total = totalPages();
                switch (btn.dataset.dir) {
                    case 'first': currentPage = 1; break;
                    case 'prev':  if (currentPage > 1) currentPage--; break;
                    case 'next':  if (currentPage < total) currentPage++; break;
                    case 'last':  currentPage = total; break;
                }
                render();
                if (scrollTarget) scrollTarget.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        });
    }
    bindArrows(pagerTop);
    bindArrows(pagerBottom);

    /* ---- Per-page change + mirror sync ---- */
    perPageSelect.addEventListener('change', function() {
        mirrors.forEach(function(m) { m.value = perPageSelect.value; });
        currentPage = 1;
        render();
    });
    mirrors.forEach(function(m) {
        m.value = perPageSelect.value;
        m.addEventListener('change', function() {
            perPageSelect.value = m.value;
            currentPage = 1;
            render();
        });
    });

    /* ---- Public API ---- */
    return {
        /** Update the displayed items (after filter/sort) and re-render */
        setItems: function(arr) {
            displayItems = arr;
            currentPage = 1;
            render();
        },
        /** Reset to page 1 without changing items */
        resetPage: function() {
            currentPage = 1;
        },
        /** Re-render with current state */
        render: render,
        /** Get all original DOM items */
        getAllItems: function() {
            return allItems;
        }
    };
}
