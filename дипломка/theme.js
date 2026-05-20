// ═══════════════════════════════════════
// 🌓 Theme Toggle (Dark / Light)
// ═══════════════════════════════════════
(function() {
  // Apply saved theme immediately (before page renders)
  const saved = localStorage.getItem('theme');
  if (saved === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Create toggle button and insert into header
    const header = document.querySelector('header');
    if (!header) return;

    const btn = document.createElement('button');
    btn.className = 'theme-toggle';
    btn.id = 'themeToggle';
    btn.title = 'Тема ауыстыру';
    btn.setAttribute('aria-label', 'Toggle dark/light theme');
    updateIcon(btn);

    // Insert before the last element in header (or append)
    const nav = header.querySelector('nav');
    const headerRight = header.querySelector('.header-right');
    if (headerRight) {
      headerRight.insertBefore(btn, headerRight.firstChild);
    } else if (nav) {
      nav.after(btn);
    } else {
      header.appendChild(btn);
    }

    btn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      
      if (next === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
      } else {
        document.documentElement.removeAttribute('data-theme');
      }
      localStorage.setItem('theme', next);
      updateIcon(btn);
    });

    // ═══════════════════════════════════════
    // 👨‍🏫 Auto-add teacher panel link for admin
    // ═══════════════════════════════════════
    const isAdmin = localStorage.getItem('isAdmin') === 'true';
    const role = localStorage.getItem('role');
    if (isAdmin || role === 'teacher') {
      const nav = header.querySelector('nav');
      if (nav && !nav.querySelector('a[href="all_results.html"]')) {
        const teacherLink = document.createElement('a');
        teacherLink.href = 'all_results.html';
        teacherLink.textContent = '👨‍🏫 Мұғалім панелі';
        teacherLink.style.fontWeight = '600';
        teacherLink.style.color = 'var(--secondary)';
        nav.appendChild(teacherLink);
      }
    }
  });

  function updateIcon(btn) {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    btn.textContent = isDark ? '☀️' : '🌙';
  }
})();
