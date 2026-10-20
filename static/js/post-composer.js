/* One composer, using the existing Django form and /feed/create/ backend. */
document.addEventListener("DOMContentLoaded", () => {
    const dialog = document.getElementById("postComposer");
    let origin = null;
    let previousOverflow = "";
    let sending = false;
    const objectURLs = new Set();

    function hasContent(form) {
        return Boolean(form.elements.caption.value.trim() || form.elements.image.files.length || form.elements.video.files.length);
    }
    function synchronize(form) {
        form.querySelector("[data-post-submit]").disabled = sending || !hasContent(form);
    }
    function previews(form) {
        const container = form.querySelector("[data-post-previews]");
        if (!container) return;
        objectURLs.forEach(url => URL.revokeObjectURL(url));
        objectURLs.clear();
        container.replaceChildren();
        for (const name of ["image", "video"]) {
            const file = form.elements[name].files[0];
            if (!file) continue;
            const figure = document.createElement("figure");
            const media = document.createElement(name === "image" ? "img" : "video");
            const url = URL.createObjectURL(file);
            objectURLs.add(url);
            media.src = url;
            if (name === "video") { media.controls = true; media.preload = "metadata"; media.playsInline = true; }
            else media.alt = "Selected photo preview";
            const caption = document.createElement("figcaption");
            caption.textContent = file.name;
            figure.append(media, caption);
            container.append(figure);
        }
    }
    document.querySelectorAll("[data-post-form]").forEach(form => {
        form.elements.image.accept = "image/*";
        form.elements.video.accept = "video/*";
        form.addEventListener("input", () => synchronize(form));
        form.addEventListener("change", event => {
            synchronize(form);
            if (event.target.type === "file") previews(form);
        });
        synchronize(form);
        form.addEventListener("submit", async event => {
            if (!hasContent(form) || sending) { event.preventDefault(); return; }
            if (!form.hasAttribute("data-post-modal")) return; // ordinary Django fallback
            event.preventDefault();
            const errorBox = form.querySelector("[data-post-errors]");
            errorBox.hidden = true;
            errorBox.replaceChildren();
            form.querySelectorAll("[aria-invalid]").forEach(field => field.removeAttribute("aria-invalid"));
            const data = new FormData(form);
            const button = form.querySelector("[data-post-submit]");
            const fields = form.querySelector("fieldset");
            sending = true;
            synchronize(form);
            button.textContent = "Posting…";
            button.setAttribute("aria-busy", "true");
            fields.disabled = true;
            dialog.querySelector("[data-post-composer-close]").disabled = true;
            try {
                const response = await fetch(form.action, {
                    method: "POST", body: data, credentials: "same-origin",
                    headers: {"X-CSRFToken": data.get("csrfmiddlewaretoken"), "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
                });
                if (response.status === 403) throw new Error("Your session or posting permissions may have changed. Refresh the page and try again.");
                if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("Please sign in again or refresh the page before posting.");
                const result = await response.json();
                if (!response.ok) {
                    const list = document.createElement("ul");
                    for (const [name, errors] of Object.entries(result.errors || {})) {
                        const field = form.elements.namedItem(name);
                        if (field?.setAttribute) field.setAttribute("aria-invalid", "true");
                        for (const error of errors) {
                            const item = document.createElement("li");
                            item.textContent = error.message;
                            list.append(item);
                        }
                    }
                    if (!list.children.length) throw new Error("Could not publish this post. Please check the content and try again.");
                    errorBox.append(list);
                    errorBox.hidden = false;
                    errorBox.focus();
                    return;
                }
                form.reset();
                objectURLs.forEach(url => URL.revokeObjectURL(url));
                objectURLs.clear();
                window.location.assign(result.redirect_url);
            } catch (error) {
                errorBox.textContent = error instanceof TypeError ? "Could not post. Check your connection and try again." : error.message;
                errorBox.hidden = false;
                errorBox.focus();
            } finally {
                sending = false;
                fields.disabled = false;
                button.textContent = "Post";
                button.removeAttribute("aria-busy");
                dialog.querySelector("[data-post-composer-close]").disabled = false;
                synchronize(form);
            }
        });
    });
    if (!dialog || typeof dialog.showModal !== "function") return;
    const endpoint = new URL(dialog.querySelector("form").action);
    document.addEventListener("click", event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
        const link = event.target.closest("a[href]");
        if (!link || link.target === "_blank") return;
        const target = new URL(link.href, location.href);
        if (target.origin !== endpoint.origin || target.pathname !== endpoint.pathname) return;
        event.preventDefault();
        origin = link;
        previousOverflow = document.body.style.overflow;
        dialog.showModal();
        document.body.style.overflow = "hidden";
        dialog.querySelector("textarea[name=caption]").focus();
    });
    dialog.querySelector("[data-post-composer-close]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("cancel", event => { if (sending) event.preventDefault(); });
    dialog.addEventListener("close", () => {
        dialog.querySelectorAll("video").forEach(video => video.pause());
        document.body.style.overflow = previousOverflow;
        const fallback = Array.from(document.querySelectorAll("[data-post-composer]")).find(link => link.getClientRects().length);
        if (origin?.getClientRects().length && !origin.closest("[inert]")) origin.focus();
        else fallback?.focus();
    });
});
