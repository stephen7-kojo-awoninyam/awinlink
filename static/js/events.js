/* Filters refine only events already returned by the existing authorized view. */
document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-event-filters]");
    if (form) {
        const cards = [...document.querySelectorAll("[data-event-card]")];
        const count = document.querySelector("[data-event-count]");
        const empty = document.querySelector("[data-filter-empty]");
        const type = form.elements.event_type;
        const category = form.elements.category;
        for (const [select, key] of [[type, "type"], [category, "category"]]) {
            const values = [...new Set(cards.map(card => card.dataset[key]).filter(Boolean))].sort();
            values.forEach(value => {
                const label = key === "type" ? cards.find(card => card.dataset.type === value).querySelector(".ev-tags span").textContent : value;
                select.add(new Option(label, value));
            });
        }
        const names = ["search", "event_type", "category", "format", "when"];
        function filter(updateURL = true) {
            const text = form.elements.search.value.trim().toLocaleLowerCase();
            let visible = 0;
            cards.forEach(card => {
                const match = (!text || card.dataset.search.toLocaleLowerCase().includes(text))
                    && (!type.value || card.dataset.type === type.value)
                    && (!category.value || card.dataset.category === category.value)
                    && (!form.elements.format.value || card.dataset.format === form.elements.format.value)
                    && (!form.elements.when.value || Date.parse(card.dataset.start) >= Date.now());
                card.hidden = !match;
                if (match) visible++;
            });
            if (count) count.textContent = `${visible} event${visible === 1 ? "" : "s"}`;
            if (empty) empty.hidden = visible > 0 || cards.length === 0;
            if (updateURL) {
                const url = new URL(location.href);
                names.forEach(name => {
                    const value = form.elements[name].value;
                    if (value) url.searchParams.set(name, value);
                    else url.searchParams.delete(name);
                });
                history.replaceState(null, "", url);
            }
        }
        function restore() {
            const params = new URLSearchParams(location.search);
            names.forEach(name => { form.elements[name].value = params.get(name) || ""; });
            filter(false);
        }
        form.hidden = false;
        form.addEventListener("submit", event => { event.preventDefault(); filter(); });
        form.addEventListener("change", () => filter());
        form.addEventListener("reset", () => setTimeout(() => filter(), 0));
        window.addEventListener("popstate", restore);
        restore();
    }
    const chart = document.querySelector("[data-event-chart]");
    const source = document.getElementById("event-registration-data");
    if (chart && source && window.Chart) {
        const entries = JSON.parse(source.textContent);
        new Chart(chart, {
            type: "line",
            data: {
                labels: entries.map(item => new Date(item.month).toLocaleDateString(undefined, {month:"short", year:"numeric"})),
                datasets: [{label:"Registrations", data:entries.map(item => item.total), borderColor:"#1769ee", backgroundColor:"#1769ee15", borderWidth:2, fill:true, tension:.3, pointRadius:4}],
            },
            options: {responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{y:{beginAtZero:true, ticks:{precision:0}, grid:{color:"#edf2fa"}}, x:{grid:{display:false}}}},
        });
    }
});
