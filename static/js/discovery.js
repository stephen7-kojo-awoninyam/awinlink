/* Categories refine only the profiles already authorized by Django. */
document.addEventListener("DOMContentLoaded", function () {
    const page = document.querySelector("[data-discovery-page]");
    const categories = page && page.querySelector("[data-discovery-categories]");
    if (!categories) return;
    const buttons = Array.from(categories.querySelectorAll("[data-discovery-category]"));
    const cards = Array.from(page.querySelectorAll("[data-discovery-card]"));
    const count = page.querySelector("[data-discovery-count]");
    const empty = page.querySelector("[data-discovery-category-empty]");
    const forms = Array.from(page.querySelectorAll("[data-discovery-search]"));
    const validCategories = new Set(buttons.map(button => button.dataset.discoveryCategory));
    categories.hidden = false;

    function selectCategory(category, updateURL = false) {
        if (!validCategories.has(category)) category = "ALL";
        let visible = 0;
        cards.forEach(card => {
            const match = category === "ALL" || card.dataset.talentCategory === category;
            card.hidden = !match;
            if (match) visible++;
        });
        buttons.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.discoveryCategory === category)));
        if (count) count.textContent = `${visible} talent${visible === 1 ? "" : "s"}`;
        if (empty) empty.hidden = visible > 0 || (category === "ALL" && page.querySelector(".discovery-talent-grid .discovery-empty-state") !== null);
        const hash = category === "ALL" ? "" : new URLSearchParams({category}).toString();
        forms.forEach(form => {
            const action = new URL(form.action, window.location.href);
            action.hash = hash;
            form.action = action.href;
        });
        if (updateURL) {
            const url = new URL(window.location.href);
            url.hash = hash;
            history.replaceState(null, "", url);
        }
    }
    buttons.forEach(button => button.addEventListener("click", () => selectCategory(button.dataset.discoveryCategory, true)));
    function fromHash() { selectCategory(new URLSearchParams(location.hash.slice(1)).get("category") || "ALL"); }
    window.addEventListener("hashchange", fromHash);
    fromHash();
});
