/* Recent-post stories: progressive enhancement over authorized Django links. */
document.addEventListener("DOMContentLoaded", () => {
    const dashboard = document.querySelector(".social-dashboard");
    if (!dashboard) return;
    const links = Array.from(dashboard.querySelectorAll("[data-story-open]"));
    const dialogs = links.map(link => document.getElementById(link.dataset.storyOpen));
    let current = -1;
    let origin = null;
    const priorOverflow = document.body.style.overflow;

    function show(index) {
        const next = dialogs[index];
        if (!next || typeof next.showModal !== "function") return false;
        const previous = dialogs[current];
        if (previous?.open) previous.close();
        current = index;
        document.body.style.overflow = "hidden";
        next.showModal();
        next.querySelector("[data-story-close]").focus();
        return true;
    }
    dialogs.forEach((dialog, index) => {
        if (!dialog) return;
        dialog.addEventListener("close", () => {
            dialog.querySelectorAll("video").forEach(video => video.pause());
            if (current === index) {
                current = -1;
                document.body.style.overflow = priorOverflow;
                origin?.focus();
            }
        });
        dialog.querySelector("[data-story-close]").addEventListener("click", () => dialog.close());
        dialog.querySelector("[data-story-previous]").addEventListener("click", () => show(index - 1));
        dialog.querySelector("[data-story-next]").addEventListener("click", () => show(index + 1));
        dialog.querySelector("footer a").addEventListener("click", () => {
            origin = null;
            dialog.close();
        });
        dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
        dialog.addEventListener("keydown", event => {
            // Native video controls keep their own keyboard shortcuts.
            if (event.target.closest("video")) return;
            if (event.key === "ArrowRight" && index < dialogs.length - 1) { event.preventDefault(); show(index + 1); }
            if (event.key === "ArrowLeft" && index > 0) { event.preventDefault(); show(index - 1); }
        });
    });
    links.forEach((link, index) => link.addEventListener("click", event => {
        // Modified clicks retain normal new-tab/link behavior.
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        origin = link;
        if (show(index)) event.preventDefault();
    }));
    const list = dashboard.querySelector(".social-story-list");
    const scroll = dashboard.querySelector("[data-stories-next]");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (list && scroll) {
        const updateScroll = () => { scroll.hidden = list.scrollWidth <= list.clientWidth + 2; };
        scroll.addEventListener("click", () => list.scrollBy({left: list.clientWidth * .7, behavior: reducedMotion.matches ? "auto" : "smooth"}));
        window.addEventListener("resize", updateScroll);
        updateScroll();
    }
    // Pause offscreen clips and clips in background tabs; never force autoplay.
    const videos = dashboard.querySelectorAll(".feed-stream video");
    if ("IntersectionObserver" in window) {
        const observer = new IntersectionObserver(entries => entries.forEach(entry => {
            if (!entry.isIntersecting) entry.target.pause();
        }), {threshold: .1});
        videos.forEach(video => observer.observe(video));
    }
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) dashboard.querySelectorAll("video").forEach(video => video.pause());
    });
});
