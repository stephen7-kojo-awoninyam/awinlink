/* Accessible local tabs and portfolio filters; every Django action stays native. */
document.addEventListener("DOMContentLoaded", function () {
    const navigation = document.querySelector("[data-profile-tabs]");
    if (navigation) {
        const tabs = Array.from(navigation.querySelectorAll("[data-profile-tab]"));
        const panels = tabs.map(tab => document.querySelector(tab.getAttribute("href")));
        navigation.setAttribute("role", "tablist");
        tabs.forEach((tab, index) => {
            tab.id = `talent-tab-${index}`;
            tab.setAttribute("role", "tab");
            tab.setAttribute("aria-controls", panels[index].id);
            panels[index].setAttribute("role", "tabpanel");
            panels[index].setAttribute("aria-labelledby", tab.id);
            panels[index].tabIndex = 0;
        });
        function select(tab, updateHash = false) {
            tabs.forEach((item, index) => {
                const selected = item === tab;
                item.setAttribute("aria-selected", String(selected));
                item.tabIndex = selected ? 0 : -1;
                panels[index].hidden = !selected;
            });
            if (updateHash) history.replaceState(null, "", tab.getAttribute("href"));
        }
        tabs.forEach((tab, index) => {
            tab.addEventListener("click", event => { event.preventDefault(); select(tab, true); });
            tab.addEventListener("keydown", event => {
                let target;
                if (event.key === "ArrowRight") target = (index + 1) % tabs.length;
                else if (event.key === "ArrowLeft") target = (index + tabs.length - 1) % tabs.length;
                else if (event.key === "Home") target = 0;
                else if (event.key === "End") target = tabs.length - 1;
                else if (event.key === " ") { event.preventDefault(); select(tab, true); return; }
                else return;
                event.preventDefault();
                select(tabs[target], true);
                tabs[target].focus();
                tabs[target].scrollIntoView({block: "nearest", inline: "nearest"});
            });
        });
        function selectFromHash() { select(tabs.find(tab => tab.getAttribute("href") === location.hash) || tabs[0]); }
        window.addEventListener("hashchange", selectFromHash);
        selectFromHash();
    }

    const filters = document.querySelector("[data-portfolio-filters]");
    if (filters) {
        const buttons = Array.from(filters.querySelectorAll("[data-portfolio-filter]"));
        const items = Array.from(document.querySelectorAll("[data-portfolio-item]"));
        const status = document.querySelector("[data-portfolio-status]");
        const empty = document.querySelector("[data-portfolio-filter-empty]");
        filters.hidden = false;
        buttons.forEach(button => {
            button.addEventListener("click", () => {
                const type = button.dataset.portfolioFilter;
                let count = 0;
                items.forEach(item => { const visible = type === "ALL" || item.dataset.itemType === type; item.hidden = !visible; if (visible) count++; });
                buttons.forEach(item => item.setAttribute("aria-pressed", String(item === button)));
                status.textContent = `${count} portfolio item${count === 1 ? "" : "s"}`;
                if (empty) empty.hidden = count !== 0 || type === "ALL";
            });
        });
    }
});
