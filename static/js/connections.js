(function () {
    const tabs = Array.from(document.querySelectorAll('[data-connections-page] [role="tab"]'));
    if (!tabs.length) return;

    function activate(tab, moveFocus) {
        tabs.forEach((item) => {
            const selected = item === tab;
            item.setAttribute("aria-selected", String(selected));
            item.tabIndex = selected ? 0 : -1;
            const panel = document.getElementById(item.getAttribute("aria-controls"));
            if (panel) panel.hidden = !selected;
        });
        if (moveFocus) tab.focus();
    }

    tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => activate(tab, false));
        tab.addEventListener("keydown", (event) => {
            let nextIndex = index;
            if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
            else if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
            else if (event.key === "Home") nextIndex = 0;
            else if (event.key === "End") nextIndex = tabs.length - 1;
            else return;
            event.preventDefault();
            activate(tabs[nextIndex], true);
        });
    });
    activate(tabs.find((tab) => tab.getAttribute("aria-selected") === "true") || tabs[0], false);

    function csrfToken() {
        const cookie = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("csrftoken="));
        return cookie ? decodeURIComponent(cookie.slice("csrftoken=".length)) : "";
    }
    async function updateGroup(url, method, body) {
        const response = await fetch(url, {
            method,
            credentials: "same-origin",
            headers: { "X-CSRFToken": csrfToken(), ...(body ? { "Content-Type": "application/json" } : {}) },
            ...(body ? { body: JSON.stringify(body) } : {})
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || data.error || "Unable to update group members.");
        window.location.reload();
    }
    document.querySelectorAll("[data-toggle-group-members]").forEach((button) => {
        button.addEventListener("click", () => {
            const panel = document.getElementById(button.getAttribute("aria-controls"));
            const expanded = button.getAttribute("aria-expanded") === "true";
            button.setAttribute("aria-expanded", String(!expanded));
            if (panel) panel.hidden = expanded;
        });
    });
    document.querySelectorAll("[data-add-member]").forEach((button) => {
        button.addEventListener("click", async () => {
            const select = button.parentElement.querySelector("[data-add-member-select]");
            if (!select || !select.value) return;
            try { await updateGroup(`/api/messaging/conversations/${button.dataset.group}/members/add/`, "POST", { user_id: select.value }); }
            catch (error) { window.alert(error.message); }
        });
    });
    document.querySelectorAll("[data-remove-member]").forEach((button) => {
        button.addEventListener("click", async () => {
            if (!window.confirm("Remove this member from the group?")) return;
            try { await updateGroup(`/api/messaging/conversations/${button.dataset.group}/members/${button.dataset.user}/remove/`, "DELETE"); }
            catch (error) { window.alert(error.message); }
        });
    });
})();
