/* Progressive enhancements for the feed's existing Django POST endpoints. */
document.addEventListener("DOMContentLoaded", function () {
    const feed = document.querySelector(".home-feed");
    if (!feed) return;
    const inFlight = new Set();

    function feedback(element, message, error = false) {
        const container = element.closest(".modal-body, .share-form, [data-feed-card], .feed-talent-row");
        const output = container && container.querySelector("[data-feed-feedback]");
        if (!output) return;
        output.textContent = message;
        output.classList.toggle("is-error", error);
        output.setAttribute("role", error ? "alert" : "status");
        output.hidden = !message;
    }

    async function request(form) {
        const token = form.querySelector("[name=csrfmiddlewaretoken]") || document.querySelector("[name=csrfmiddlewaretoken]");
        const response = await fetch(form.action, {
            method: "POST", credentials: "same-origin", body: new FormData(form),
            headers: { "X-CSRFToken": token ? token.value : "", "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" }
        });
        if (!response.headers.get("content-type")?.includes("application/json")) {
            throw new Error("This action could not be completed. Please refresh the page and try again.");
        }
        const data = await response.json();
        if (!response.ok || data.status === "error") throw new Error(data.message || data.detail || "This action could not be completed.");
        return data;
    }

    function matchingCards(kind, id) {
        return Array.from(feed.querySelectorAll("[data-feed-card]")).filter(card => card.dataset.kind === kind && card.dataset.postId === id);
    }

    // Prevent duplicate toggles when an original post and its repost both appear.
    function bindForms(selector, key, update) {
        feed.querySelectorAll(selector).forEach(form => {
            form.addEventListener("submit", async event => {
                event.preventDefault();
                if (!form.checkValidity()) { form.reportValidity(); return; }
                const operation = key(form);
                if (inFlight.has(operation)) return;
                inFlight.add(operation);
                const button = form.querySelector("button[type=submit]");
                const wasDisabled = button?.disabled;
                let keepDisabled = false;
                if (button) { button.disabled = true; button.setAttribute("aria-busy", "true"); }
                feedback(form, "");
                try {
                    const data = await request(form);
                    keepDisabled = update(form, data) === true;
                } catch (error) {
                    feedback(form, error.message, true);
                } finally {
                    inFlight.delete(operation);
                    if (button) { button.disabled = Boolean(wasDisabled) || keepDisabled; button.removeAttribute("aria-busy"); }
                }
            });
        });
    }

    bindForms(".feed-like-form", form => `like:${form.dataset.kind}:${form.dataset.postId}`, (form, data) => {
        matchingCards(form.dataset.kind, form.dataset.postId).forEach(card => {
            const button = card.querySelector(".feed-like-form button");
            const liked = Boolean(data.liked);
            button.dataset.liked = String(liked);
            button.setAttribute("aria-pressed", String(liked));
            button.classList.toggle("is-active", liked);
            button.querySelector("i").className = `bi ${liked ? "bi-heart-fill" : "bi-heart"}`;
            button.querySelector(".like-count").textContent = data.count;
        });
        feedback(form, data.liked ? "Liked." : "Like removed.");
    });

    bindForms(".feed-save-form", form => `save:${form.dataset.postId}`, (form, data) => {
        matchingCards("post", form.dataset.postId).forEach(card => {
            const button = card.querySelector(".save-button");
            const saved = Boolean(data.saved);
            button.dataset.saved = String(saved);
            button.setAttribute("aria-pressed", String(saved));
            button.classList.toggle("is-active", saved);
            button.querySelector("i").className = `bi ${saved ? "bi-bookmark-fill" : "bi-bookmark"}`;
            button.querySelector(".save-label").textContent = saved ? "Saved" : "Save";
        });
        feedback(form, data.saved ? "Post saved." : "Post removed from saved posts.");
    });

    feed.querySelectorAll(".feed-comment-focus").forEach(button => {
        button.addEventListener("click", () => {
            const comments = document.getElementById(button.dataset.commentTarget);
            if (!comments) return;
            comments.open = true;
            comments.querySelector("input[name=text]")?.focus();
        });
    });

    bindForms(".feed-comment-form", form => `comment:${form.dataset.kind}:${form.dataset.postId}`, (form, data) => {
        matchingCards(form.dataset.kind, form.dataset.postId).forEach(card => {
            card.querySelectorAll("[data-comment-count]").forEach(count => { count.textContent = data.count; });
            const list = card.querySelector("[data-comments-list]");
            list.querySelector("[data-no-comments]")?.remove();
            const comment = document.createElement("div");
            comment.className = "feed-comment";
            const author = document.createElement("strong");
            author.textContent = data.comment.user;
            const text = document.createElement("p");
            text.textContent = data.comment.text;
            const time = document.createElement("small");
            time.className = "text-muted";
            time.textContent = data.comment.created_at;
            comment.append(author, text, time);
            list.prepend(comment);
        });
        form.querySelector("input[name=text]").value = "";
        feedback(form, "Comment posted.");
    });

    bindForms(".share-form", form => `share:${form.dataset.postId}`, (form, data) => {
        matchingCards("post", form.dataset.postId).forEach(card => {
            card.querySelectorAll(".share-count").forEach(count => { count.textContent = data.count; });
        });
        form.reset();
        const modal = form.closest(".modal");
        if (modal && window.bootstrap?.Modal) window.bootstrap.Modal.getOrCreateInstance(modal).hide();
        const card = form.closest("[data-feed-card]");
        feedback(card, "Post shared with your network.");
    });

    bindForms(".connection-request-form", form => `connection:${form.action}`, (form, data) => {
        const button = form.querySelector("button");
        const states = { request_sent: "Request sent", incoming_request: "Request received", connected: "Connected" };
        button.textContent = states[data.state] || "Request sent";
        button.className = "btn btn-sm btn-light";
        // Keep successful requests disabled until a fresh render provides the
        // server's current connection id and permitted next actions.
        feedback(form, data.detail || button.textContent);
        return true;
    });

    bindForms(".connection-state-form", form => `connection-state:${form.closest('.feed-talent-row').querySelector('.feed-suggestion-person').href}`, (form, data) => {
        const row = form.closest(".feed-talent-row");
        const actions = row.querySelector(".feed-connection-actions");
        actions.querySelectorAll(".connection-state-form, .connection-request-form").forEach(item => item.remove());
        const state = document.createElement("span");
        state.className = "feed-connected";
        state.textContent = data.state === "connected" ? "Connected" : data.detail || "Request updated.";
        actions.append(state);
        feedback(row, data.detail || state.textContent);
    });
});
