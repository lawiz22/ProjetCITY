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
});