function normalizeCellValue(value) {
    const cleaned = (value || '').toString().trim();
    const numeric = Number(cleaned.replace(/\s/g, '').replace(/,/g, '').replace(/%/g, ''));
    if (!Number.isNaN(numeric) && cleaned !== '') {
        return { type: 'number', value: numeric };
    }
    return { type: 'text', value: cleaned.toLowerCase() };
}

function enhanceTable(table) {
    const wrapper = table.closest('.table-wrapper');
    const tbody = table.querySelector('tbody');
    const headers = Array.from(table.querySelectorAll('thead th'));
    if (!wrapper || !tbody || headers.length === 0) {
        return;
    }

    const toolbar = document.createElement('div');
    toolbar.className = 'table-toolbar';
    toolbar.innerHTML = '<input type="text" class="table-search" placeholder="Filtrer le tableau...">';
    wrapper.parentElement.insertBefore(toolbar, wrapper);

    const searchInput = toolbar.querySelector('.table-search');
    const originalRows = Array.from(tbody.querySelectorAll('tr'));
    let sortState = { index: -1, direction: 'asc' };

    function applyTableState() {
        const searchTerm = searchInput.value.trim().toLowerCase();
        let rows = [...originalRows];

        if (sortState.index >= 0) {
            rows.sort((rowA, rowB) => {
                const valueA = normalizeCellValue(rowA.children[sortState.index]?.textContent || '');
                const valueB = normalizeCellValue(rowB.children[sortState.index]?.textContent || '');
                let result = 0;
                if (valueA.type === 'number' && valueB.type === 'number') {
                    result = valueA.value - valueB.value;
                } else {
                    result = valueA.value.localeCompare(valueB.value, 'fr');
                }
                return sortState.direction === 'asc' ? result : -result;
            });
        }

        rows.forEach((row) => {
            const text = row.textContent.toLowerCase();
            row.style.display = !searchTerm || text.includes(searchTerm) ? '' : 'none';
            tbody.appendChild(row);
        });
    }

    headers.forEach((header, index) => {
        header.classList.add('sortable-header');
        header.addEventListener('click', () => {
            if (sortState.index === index) {
                sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
            } else {
                sortState = { index, direction: 'asc' };
            }
            headers.forEach((cell) => cell.dataset.sortDirection = '');
            header.dataset.sortDirection = sortState.direction;
            applyTableState();
        });
    });

    searchInput.addEventListener('input', applyTableState);
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('table[data-sortable-table], .table-wrapper table').forEach(enhanceTable);
});