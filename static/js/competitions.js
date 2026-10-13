/* Refine the server's authorized search results without altering GET filters. */
document.addEventListener("DOMContentLoaded", () => {
    const filters = document.querySelector("[data-competition-refinements]");
    if (!filters) return;
    const cards = [...document.querySelectorAll("[data-competition-results] [data-competition-card]")];
    const stage = filters.querySelector("[name=stage]");
    const format = filters.querySelector("[name=format]");
    const count = document.querySelector("[data-competition-count]");
    const empty = document.querySelector("[data-competition-empty]");
    const groups = {
        registration: ["PUBLISHED"],
        active: ["REGISTRATION_CLOSED", "ONGOING", "JUDGING"],
        results: ["RESULTS", "COMPLETED"],
    };
    function apply(updateURL = true) {
        let visible = 0;
        cards.forEach(card => {
            const match = (!format.value || card.dataset.format === format.value)
                && (!stage.value || (groups[stage.value] || []).includes(card.dataset.status));
            card.hidden = !match;
            if (match) visible++;
        });
        if (count) count.textContent = `${visible} competition${visible === 1 ? "" : "s"}`;
        if (empty) empty.hidden = visible > 0 || cards.length === 0;
        const params = new URLSearchParams();
        if (stage.value) params.set("stage", stage.value);
        if (format.value) params.set("format", format.value);
        const hash = params.toString();
        document.querySelectorAll("[data-category-link]").forEach(link => {
            const url = new URL(link.href, location.href);
            url.hash = hash;
            link.href = url.href;
        });
        const search = document.querySelector("[data-competition-search]");
        if (search) {
            const action = new URL(search.action, location.href);
            action.hash = hash;
            search.action = action.href;
        }
        if (updateURL) {
            const url = new URL(location.href);
            url.hash = hash;
            history.replaceState(null, "", url);
        }
    }
    function restore() {
        const params = new URLSearchParams(location.hash.slice(1));
        stage.value = params.get("stage") || "";
        format.value = params.get("format") || "";
        apply(false);
    }
    filters.hidden = false;
    filters.addEventListener("change", () => apply());
    filters.querySelector("[data-clear-refinements]").addEventListener("click", () => {
        stage.value = ""; format.value = ""; apply();
    });
    window.addEventListener("hashchange", restore);
    window.addEventListener("popstate", restore);
    restore();
});
