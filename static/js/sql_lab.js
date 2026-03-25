function mountSqlSnippetButtons() {
    const textarea = document.querySelector('.sql-form textarea[name="sql"]');
    if (!textarea) {
        return;
    }

    document.querySelectorAll('.sql-snippet-card').forEach((card) => {
        const button = card.querySelector('.sql-use-snippet');
        const snippet = card.dataset.sqlSnippet;
        if (!button || !snippet) {
            return;
        }
        button.addEventListener('click', () => {
            textarea.value = snippet;
            textarea.focus();
            textarea.setSelectionRange(0, textarea.value.length);
        });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    mountSqlSnippetButtons();
});