/* Presentation enhancements only. Messaging, sound, and calls keep their existing clients. */
document.addEventListener("DOMContentLoaded", function () {
    const filters = document.querySelector("[data-notification-filters]");
    if (filters) {
        const cards = Array.from(document.querySelectorAll("[data-notification-card]"));
        const buttons = Array.from(filters.querySelectorAll("[data-notification-filter]"));
        const empty = document.querySelector("[data-notification-empty]");
        filters.hidden = cards.length === 0;
        buttons.forEach(button => button.addEventListener("click", function () {
            const filter = button.dataset.notificationFilter;
            let visible = 0;
            cards.forEach(card => {
                const matches = filter === "all" || (filter === "unread" && card.dataset.unread === "true") || (filter === "calls" && ["INCOMING_CALL", "MISSED_CALL"].includes(card.dataset.notificationType));
                card.hidden = !matches;
                if (matches) visible++;
            });
            buttons.forEach(item => item.setAttribute("aria-pressed", String(item === button)));
            if (empty) empty.hidden = visible > 0;
        }));
    }
    document.querySelectorAll("label.attachment-button[for]").forEach(label => {
        label.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                document.getElementById(label.htmlFor)?.click();
            }
        });
    });
});
