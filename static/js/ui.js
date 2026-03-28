function getCurrentTheme() {
    return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

function applyTheme(theme) {
    const nextTheme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = nextTheme;
    localStorage.setItem('projetcity-theme', nextTheme);
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
        button.textContent = nextTheme === 'dark' ? 'Mode clair' : 'Mode sombre';
    });
    document.dispatchEvent(new CustomEvent('projetcity:themechange', { detail: { theme: nextTheme } }));
}

document.addEventListener('DOMContentLoaded', () => {
    applyTheme(getCurrentTheme());
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
        button.addEventListener('click', () => {
            applyTheme(getCurrentTheme() === 'dark' ? 'light' : 'dark');
        });
    });

    // Sidebar collapse toggle
    const shell = document.querySelector('.site-shell');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    if (shell && sidebarToggle) {
        if (localStorage.getItem('projetcity-sidebar') === 'collapsed') {
            shell.classList.add('sidebar-collapsed');
        }
        document.documentElement.classList.remove('sidebar-pre-collapsed');
        sidebarToggle.addEventListener('click', () => {
            shell.classList.toggle('sidebar-collapsed');
            localStorage.setItem('projetcity-sidebar',
                shell.classList.contains('sidebar-collapsed') ? 'collapsed' : 'open');
            window.dispatchEvent(new Event('resize'));
        });
    }
});