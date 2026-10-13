/* Existing services remain authoritative for permissions and every team transition. */
document.addEventListener("DOMContentLoaded", function () {
    const workspace = document.querySelector("[data-organization-workspace]");
    const responsePage = document.querySelector("[data-team-response]");
    const csrf = () => document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
    const make = (tag, text, className) => { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if (className) element.className = className; return element; };
    function report(output, message, error = false) {
        if (!output) return;
        output.textContent = message;
        output.classList.toggle("is-error", error);
        output.setAttribute("role", error ? "alert" : "status");
        output.hidden = !message;
    }
    function errorText(data) {
        if (typeof data === "string") return data;
        if (Array.isArray(data)) return data.map(errorText).join(" ");
        if (data && typeof data === "object") return Object.values(data).map(errorText).join(" ");
        return "This action could not be completed.";
    }
    async function request(url, method = "GET", data) {
        const options = {method, credentials: "same-origin", cache: "no-store", headers: {"Accept": "application/json"}};
        if (method !== "GET") { options.headers["X-CSRFToken"] = csrf(); options.headers["Content-Type"] = "application/json"; options.body = JSON.stringify(data || {}); }
        const response = await fetch(url, options);
        if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("Please refresh the page and try again.");
        const result = await response.json();
        if (!response.ok) throw new Error(errorText(result));
        return result;
    }

    if (responsePage) {
        const form = responsePage.querySelector("[data-team-response-form]");
        const output = responsePage.querySelector("[data-response-feedback]");
        const token = new URLSearchParams(location.hash.slice(1)).get("token");
        if (token) { if (form) form.elements.token.value = token; history.replaceState(null, "", location.pathname + location.search); }
        if (form && new Date(responsePage.dataset.expiry).getTime() <= Date.now()) {
            form.hidden = true;
            report(output, "This invitation has expired. Ask the organization owner for a new invitation.");
        } else if (form) {
            form.addEventListener("submit", async event => {
                event.preventDefault();
                if (!form.reportValidity() || form.dataset.busy === "true") return;
                form.dataset.busy = "true";
                const buttons = Array.from(form.querySelectorAll("button"));
                buttons.forEach(button => { button.disabled = true; });
                report(output, "");
                try {
                    const action = event.submitter?.hasAttribute("formaction") ? event.submitter.formAction : form.action;
                    const data = await request(action, "POST", {token: form.elements.token.value});
                    form.elements.token.value = "";
                    form.hidden = true;
                    responsePage.querySelector("[data-invitation-status]").textContent = data.status.toLowerCase();
                    report(output, data.status === "ACCEPTED" ? "Invitation accepted. Your team membership is now active." : "Invitation declined.");
                    if (data.status === "ACCEPTED") {
                        const link = document.querySelector("[data-invitation-workspace-link]")?.content.firstElementChild;
                        if (link) output.after(link.cloneNode(true));
                    }
                } catch (error) { report(output, error.message, true); }
                finally { form.dataset.busy = "false"; buttons.forEach(button => { button.disabled = false; }); }
            });
        }
    }
    if (!workspace || workspace.dataset.manageMembers !== "true") return;
    const memberOutput = workspace.querySelector("[data-members-feedback]");
    const invitationOutput = workspace.querySelector("[data-invitations-feedback]");
    const membersBody = workspace.querySelector("[data-team-members]");
    const invitationsBody = workspace.querySelector("[data-team-invitations]");
    const inviteForm = workspace.querySelector("[data-team-invite-form]");
    const confirmation = workspace.querySelector("[data-team-confirm]");
    let busy = false;
    let createdInvitationId = null;

    function endpoint(pattern, id, resource = "members") {
        if (!Number.isInteger(id) || id <= 0) throw new Error("Invalid team record.");
        return pattern.replace(`/${resource}/0/`, `/${resource}/${id}/`);
    }
    async function confirm(title, description) {
        if (!confirmation?.showModal) return window.confirm(`${title}\n\n${description}`);
        if (confirmation.open) return false;
        confirmation.querySelector("[data-confirm-title]").textContent = title;
        confirmation.querySelector("[data-confirm-description]").textContent = description;
        confirmation.returnValue = "";
        return new Promise(resolve => {
            confirmation.addEventListener("close", () => resolve(confirmation.returnValue === "confirm"), {once: true});
            confirmation.showModal();
        });
    }
    async function mutate(operation, output) {
        if (busy) return;
        busy = true;
        const buttons = Array.from(workspace.querySelectorAll("[data-team-members] button, [data-team-invitations] button, [data-refresh-team], [data-team-invite-form] button"));
        const disabled = buttons.map(button => button.disabled);
        buttons.forEach(button => { button.disabled = true; });
        report(output, "");
        try { await operation(); }
        catch (error) { report(output, error.message, true); }
        finally { busy = false; buttons.forEach((button, index) => { button.disabled = disabled[index]; }); }
    }
    function renderMembers(members) {
        membersBody.replaceChildren();
        if (!members.length) { const row = make("tr"); const cell = make("td", "No team memberships yet. Invite a colleague to get started."); cell.colSpan = 4; row.append(cell); membersBody.append(row); return; }
        members.forEach(member => {
            const row = make("tr");
            const nameCell = make("td", `@${member.username}${String(member.user) === workspace.dataset.currentUser ? " (you)" : ""}`);
            nameCell.dataset.label = "Member"; row.append(nameCell);
            const roleCell = make("td");
            roleCell.dataset.label = "Role";
            if (member.role === "OWNER") roleCell.append(make("span", "Owner", "workspace-role"));
            else {
                const form = make("form", undefined, "workspace-member-role-form");
                const select = make("select"); select.setAttribute("aria-label", `Role for @${member.username}`);
                ["MANAGER", "RECRUITER", "VIEWER"].forEach(role => { const option = make("option", role.toLowerCase()); option.value = role; option.selected = member.role === role; select.append(option); });
                select.disabled = member.status === "REMOVED";
                const save = make("button", "Save", "workspace-small-button"); save.type = "submit"; save.disabled = select.disabled;
                form.append(select, save);
                form.addEventListener("submit", event => { event.preventDefault(); mutate(async () => {
                    await request(endpoint(workspace.dataset.memberRoleUrl, member.id), "PATCH", {role: select.value});
                    await loadMembers(); report(memberOutput, "Team role updated.");
                }, memberOutput); });
                roleCell.append(form);
            }
            const statusCell = make("td", member.status.toLowerCase()); statusCell.dataset.label = "Status";
            row.append(roleCell, statusCell);
            const actions = make("td"); const group = make("div", undefined, "workspace-member-actions");
            actions.dataset.label = "Actions";
            if (member.role !== "OWNER") {
                const action = member.status === "ACTIVE" ? "suspend" : "restore";
                const button = make("button", action, "workspace-small-button"); button.type = "button";
                button.addEventListener("click", async () => {
                    if (await confirm(`${action === "suspend" ? "Suspend" : "Restore"} @${member.username}?`, "This changes access to this organization only.")) mutate(async () => {
                        const pattern = action === "suspend" ? workspace.dataset.memberSuspendUrl : workspace.dataset.memberRestoreUrl;
                        await request(endpoint(pattern, member.id), "POST"); await loadMembers(); report(memberOutput, "Team access updated.");
                    }, memberOutput);
                });
                group.append(button);
                if (member.status !== "REMOVED") {
                    const remove = make("button", "Remove", "workspace-small-button is-danger"); remove.type = "button";
                    remove.addEventListener("click", async () => { if (await confirm(`Remove @${member.username}?`, "Their membership will be marked as removed. Their account and other organizations are unaffected.")) mutate(async () => {
                        await request(endpoint(workspace.dataset.memberRemoveUrl, member.id), "POST"); await loadMembers(); report(memberOutput, "Member removed from this organization.");
                    }, memberOutput); });
                    group.append(remove);
                }
                if (member.status === "ACTIVE" && workspace.dataset.transferOwner === "true") {
                    const transfer = make("button", "Transfer ownership", "workspace-small-button"); transfer.type = "button";
                    transfer.addEventListener("click", async () => { if (await confirm(`Transfer ownership to @${member.username}?`, "They will become the owner. You will become a manager and lose access to owner-only team controls.")) mutate(async () => {
                        await request(workspace.dataset.transferUrl, "POST", {membership_id: member.id});
                        const url = new URL(location.href); url.searchParams.set("organization_id", workspace.dataset.organizationId); location.assign(url.href);
                    }, memberOutput); });
                    group.append(transfer);
                }
            } else group.append(make("span", "Ownership is protected", "workspace-empty-copy"));
            actions.append(group); row.append(actions); membersBody.append(row);
        });
    }
    function renderInvitations(invitations) {
        invitationsBody.replaceChildren();
        if (!invitations.length) { invitationsBody.append(make("p", "No team invitations yet.", "workspace-empty-copy")); return; }
        invitations.forEach(invitation => {
            const row = make("article", undefined, "workspace-invitation-row");
            const copy = make("div"); copy.append(make("strong", `@${invitation.recipient_username}`), make("small", `${invitation.role.toLowerCase()} · Expires ${new Date(invitation.expires_at).toLocaleDateString()}`));
            const expired = new Date(invitation.expires_at).getTime() <= Date.now();
            row.append(copy, make("span", invitation.status === "PENDING" && expired ? "expired" : invitation.status.toLowerCase(), "workspace-status"));
            if (invitation.status === "PENDING" && !expired) {
                const revoke = make("button", "Revoke", "workspace-small-button is-danger"); revoke.type = "button";
                revoke.addEventListener("click", async () => { if (await confirm(`Revoke invitation for @${invitation.recipient_username}?`, "This invitation will no longer be usable.")) mutate(async () => {
                    await request(endpoint(workspace.dataset.revokeUrl, invitation.id, "invitations"), "POST");
                    if (invitation.id === createdInvitationId) { workspace.querySelector("[data-created-invite-link]").value = ""; workspace.querySelector("[data-invite-link-panel]").hidden = true; createdInvitationId = null; }
                    await loadInvitations(); report(invitationOutput, "Invitation revoked.");
                }, invitationOutput); });
                row.append(revoke);
            }
            invitationsBody.append(row);
        });
    }
    async function loadMembers() { renderMembers(await request(workspace.dataset.membersUrl)); }
    async function loadInvitations() { renderInvitations(await request(workspace.dataset.invitationsUrl)); }
    async function refresh() {
        await Promise.allSettled([
            loadMembers().catch(error => { membersBody.replaceChildren(); report(memberOutput, error.message, true); }),
            loadInvitations().catch(error => { invitationsBody.replaceChildren(); report(invitationOutput, error.message, true); }),
        ]);
    }
    workspace.querySelector("[data-refresh-team]").addEventListener("click", refresh);
    inviteForm.addEventListener("submit", event => {
        event.preventDefault();
        if (!inviteForm.reportValidity()) return;
        mutate(async () => {
            const data = await request(workspace.dataset.invitationsUrl, "POST", {recipient_username: inviteForm.elements.recipient_username.value, role: inviteForm.elements.role.value, expires_at: new Date(Date.now() + Number(inviteForm.elements.days.value) * 86400000).toISOString()});
            const link = new URL(data.response_url, location.origin); link.hash = new URLSearchParams({token: data.token}).toString();
            createdInvitationId = data.invitation.id;
            workspace.querySelector("[data-created-invite-link]").value = link.href;
            workspace.querySelector("[data-invite-link-panel]").hidden = false;
            inviteForm.reset(); await loadInvitations(); report(invitationOutput, "Invitation created. Share the private link with the recipient.");
        }, invitationOutput);
    });
    workspace.querySelector("[data-copy-invite]").addEventListener("click", async () => {
        const input = workspace.querySelector("[data-created-invite-link]");
        try { await navigator.clipboard.writeText(input.value); report(invitationOutput, "Invitation link copied."); }
        catch { input.focus(); input.select(); report(invitationOutput, "Select and copy the invitation link."); }
    });
    refresh();
});
