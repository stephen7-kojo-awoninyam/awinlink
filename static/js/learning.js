document.addEventListener("DOMContentLoaded", () => {
    function alignNavigation() {
        const navigation = document.querySelector(".lc-nav");
        const activeLink = navigation && navigation.querySelector('[aria-current="page"]');
        if (activeLink) {
            const offset = activeLink.getBoundingClientRect().left - navigation.getBoundingClientRect().left;
            navigation.scrollLeft = Math.max(0, offset - (navigation.clientWidth - activeLink.clientWidth) / 2);
        }
    }
    alignNavigation();
    document.addEventListener("submit", async event => {
        if (event.defaultPrevented) return;
        const form = event.target.closest("form[data-learning-return]");
        if (!form || !window.fetch) return;
        event.preventDefault();
        if (form.dataset.saving === "true") return;
        form.dataset.saving = "true";
        const button = form.querySelector('button[type="submit"]');
        const body = new FormData(form);
        if (button) button.disabled = true;
        const previousError = form.querySelector("[data-save-error]");
        if (previousError) previousError.remove();
        try {
            const response = await fetch(form.action || location.href, {method:"POST", body, credentials:"same-origin"});
            if (!response.ok) throw new Error("The save could not be confirmed.");
            if (response.redirected) {
                const destination = new URL(response.url);
                const legacy = new URL(form.dataset.learningLegacyReturn, location.href);
                location.assign(destination.pathname === legacy.pathname ? form.dataset.learningReturn : response.url);
                return;
            }
            const markup = await response.text();
            const updated = new DOMParser().parseFromString(markup,"text/html").querySelector(".learning-page");
            if (!updated) throw new Error("The response could not be displayed.");
            const page = document.querySelector(".learning-page");
            if (page) { page.replaceWith(updated); alignNavigation(); }
        } catch (_) {
            const notice = document.createElement("p");
            notice.className = "lc-notice";
            notice.dataset.saveError = "";
            notice.setAttribute("role","alert");
            notice.textContent = "We couldn’t confirm this change. Reload the page to check its status before trying again.";
            form.append(notice);
        } finally {
            form.dataset.saving = "false";
            if (button) button.disabled = false;
        }
    });
    const viewer = document.querySelector("[data-lesson-viewer]");
    if (viewer) {
        const video = viewer.querySelector("video");
        const focus = viewer.querySelector("[data-focus-video]");
        if (focus) focus.addEventListener("click", () => {
            const enabled = viewer.classList.toggle("is-focused");
            focus.setAttribute("aria-pressed", String(enabled));
            focus.textContent = enabled ? "Exit focus" : "Focus view";
        });
        if (video) {
            const speed = viewer.querySelector("[data-video-speed]");
            if (speed) speed.addEventListener("change", () => { video.playbackRate = Number(speed.value); });
            const error = viewer.querySelector("[data-video-error]");
            const showMediaError = () => { if (error) error.hidden = false; };
            video.addEventListener("error", showMediaError);
            video.querySelectorAll("source").forEach(source => source.addEventListener("error", showMediaError));
            const key = `awinlink-lesson-${viewer.dataset.userId}-${viewer.dataset.lessonId}`;
            const resume = viewer.querySelector("[data-video-resume]");
            let saved = 0;
            try { saved = Number(localStorage.getItem(key)) || 0; } catch (_) { /* Playback works without local storage. */ }
            let resumeDismissed = false;
            function offerResume() {
                if (resume && !resumeDismissed && saved > 5 && Number.isFinite(video.duration) && saved < video.duration - 3) {
                    resume.querySelector("[data-resume-time]").textContent = `${Math.floor(saved / 60)}:${String(Math.floor(saved % 60)).padStart(2,"0")}`;
                    resume.hidden = false;
                }
            }
            video.addEventListener("loadedmetadata", offerResume);
            video.addEventListener("durationchange", offerResume);
            if (resume) {
                resume.querySelector("[data-resume-playback]").addEventListener("click", () => { video.currentTime = saved; resume.hidden = true; resumeDismissed = true; });
                resume.querySelector("[data-start-over]").addEventListener("click", () => { video.currentTime = 0; resume.hidden = true; resumeDismissed = true; });
            }
            let lastSaved = 0;
            function remember() {
                try { localStorage.setItem(key,String(video.currentTime)); } catch (_) { /* Optional browser preference. */ }
            }
            video.addEventListener("timeupdate", () => {
                if (Math.abs(video.currentTime - lastSaved) > 5) { lastSaved = video.currentTime; remember(); }
            });
            video.addEventListener("pause", remember);
            video.addEventListener("ended", () => { try { localStorage.removeItem(key); } catch (_) {} });
        }
    }
    const quiz = document.querySelector("[data-quiz-form]");
    if (quiz) {
        const count = quiz.querySelector("[data-answer-count]");
        function update() {
            const answered = new Set([...quiz.querySelectorAll('input[type="radio"]:checked')].map(input => input.name)).size;
            const total = quiz.querySelectorAll("fieldset").length;
            if (count) count.textContent = `${answered} of ${total} answered`;
        }
        quiz.addEventListener("change", update);
        update();
    }
});
