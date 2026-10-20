/* Accessibility and responsive navigation for the shared application shell. */
document.addEventListener("DOMContentLoaded", function () {
    const sidebar = document.getElementById("awinlinkSidebar");
    if (!sidebar) return;

    const mobile = window.matchMedia("(max-width: 991.98px)");
    const overlay = document.getElementById("sidebarOverlay");
    const closeButton = document.getElementById("sidebarCloseButton");
    const menuButton = document.getElementById("mobileSidebarToggle");
    const moreButton = document.getElementById("mobileMoreToggle");
    const main = document.querySelector(".awinlink-main");
    const topbar = document.querySelector(".mobile-topbar");
    const bottomNav = document.querySelector(".mobile-bottom-nav");
    let returnFocus = null;
    const previousOverflow = document.body.style.overflow;

    function synchronizeDrawer() {
        const open = mobile.matches && sidebar.classList.contains("show");
        sidebar.inert = mobile.matches && !open;
        [main, topbar, bottomNav].forEach(function (element) {
            if (element) element.inert = open;
        });
        [menuButton, moreButton].forEach(function (button) {
            if (button) button.setAttribute("aria-expanded", String(open));
        });
        if (open) {
            sidebar.setAttribute("role", "dialog");
            sidebar.setAttribute("aria-modal", "true");
        } else {
            sidebar.removeAttribute("role");
            sidebar.removeAttribute("aria-modal");
        }
    }

    function openDrawer(trigger) {
        if (!mobile.matches) return;
        // main.js retains its existing menu listener; keep these hooks compatible.
        returnFocus = trigger;
        sidebar.classList.add("show");
        if (overlay) overlay.classList.add("show");
        document.body.style.overflow = "hidden";
        synchronizeDrawer();
        if (closeButton) closeButton.focus();
    }

    function closeDrawer(restoreFocus) {
        sidebar.classList.remove("show");
        if (overlay) overlay.classList.remove("show");
        document.body.style.overflow = previousOverflow;
        synchronizeDrawer();
        if (restoreFocus && returnFocus) returnFocus.focus();
        returnFocus = null;
    }

    [menuButton, moreButton].forEach(function (button) {
        if (button) button.addEventListener("click", function () { openDrawer(button); });
    });
    if (closeButton) closeButton.addEventListener("click", function () { closeDrawer(true); });
    if (overlay) overlay.addEventListener("click", function () { closeDrawer(true); });
    sidebar.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", function () { if (mobile.matches) closeDrawer(false); });
    });
    document.addEventListener("keydown", function (event) {
        if (!mobile.matches || !sidebar.classList.contains("show")) return;
        if (event.key === "Escape") {
            event.preventDefault();
            closeDrawer(true);
        }
        if (event.key === "Tab") {
            const focusable = Array.from(sidebar.querySelectorAll("a[href], button, input:not([type='hidden'])"))
                .filter(function (element) { return !element.disabled && element.getClientRects().length; });
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    });
    mobile.addEventListener("change", function () { closeDrawer(false); });
    synchronizeDrawer();

    // Match the most specific destination, including detail pages inside a section.
    [sidebar, bottomNav].forEach(function (navigation) {
        if (!navigation) return;
        const links = Array.from(navigation.querySelectorAll("a.sidebar-link, a.mobile-nav-link"));
        const path = window.location.pathname;
        const matches = links.filter(function (link) {
            const target = new URL(link.href, window.location.href);
            const href = target.pathname;
            const view = new URL(window.location.href).searchParams.get("view");
            if (target.searchParams.has("view") && target.searchParams.get("view") !== view) return false;
            if (!target.searchParams.has("view") && href === path && view === "reels") return false;
            return href === path || (href !== "/" && href.endsWith("/") && path.startsWith(href));
        });
        const longest = Math.max(0, ...matches.map(function (link) { return new URL(link.href).pathname.length; }));
        links.forEach(function (link) {
            const active = matches.includes(link) && new URL(link.href).pathname.length === longest;
            link.classList.toggle("active", active);
            if (active) link.setAttribute("aria-current", "page");
            else link.removeAttribute("aria-current");
        });
    });
    sidebar.querySelectorAll(".sidebar-link i").forEach(function (icon) {
        icon.setAttribute("aria-hidden", "true");
    });
});
