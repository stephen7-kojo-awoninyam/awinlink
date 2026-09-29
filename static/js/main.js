/* =========================================================
   AWINLINK MAIN JAVASCRIPT
========================================================= */

document.addEventListener("DOMContentLoaded", function () {


    /* =====================================================
       MOBILE SIDEBAR
    ===================================================== */

    const sidebar =
        document.getElementById("awinlinkSidebar");

    const sidebarToggle =
        document.getElementById("mobileSidebarToggle");

    const sidebarOverlay =
        document.getElementById("sidebarOverlay");


    function openSidebar() {

        if (!sidebar) {
            return;
        }

        sidebar.classList.add("show");

        if (sidebarOverlay) {
            sidebarOverlay.classList.add("show");
        }

        document.body.style.overflow = "hidden";
    }


    function closeSidebar() {

        if (!sidebar) {
            return;
        }

        sidebar.classList.remove("show");

        if (sidebarOverlay) {
            sidebarOverlay.classList.remove("show");
        }

        document.body.style.overflow = "";
    }


    if (sidebarToggle) {

        sidebarToggle.addEventListener(
            "click",
            openSidebar
        );

    }


    if (sidebarOverlay) {

        sidebarOverlay.addEventListener(
            "click",
            closeSidebar
        );

    }


    /* =====================================================
       CLOSE MOBILE SIDEBAR AFTER CLICKING LINK
    ===================================================== */

    if (sidebar) {

        const sidebarLinks =
            sidebar.querySelectorAll(".sidebar-link");

        sidebarLinks.forEach(function (link) {

            link.addEventListener(
                "click",
                function () {

                    if (
                        window.innerWidth <= 991
                    ) {

                        closeSidebar();

                    }

                }
            );

        });

    }


    /* =====================================================
       ACTIVE SIDEBAR LINK
    ===================================================== */

    const currentPath =
        window.location.pathname;

    const links =
        document.querySelectorAll(
            ".sidebar-link"
        );


    links.forEach(function (link) {

        const href =
            link.getAttribute("href");


        if (
            href &&
            href !== "#" &&
            currentPath === href
        ) {

            link.classList.add("active");

        }

    });


    /* =====================================================
       GLOBAL SEARCH
    ===================================================== */

    const searchInput =
        document.getElementById(
            "globalSearch"
        );


    if (searchInput) {

        searchInput.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key === "Enter"
                ) {

                    const query =
                        searchInput.value.trim();


                    if (query.length > 0) {

                        console.log(
                            "Awinlink search:",
                            query
                        );

                        /*
                         * We will connect this
                         * to the real Awinlink
                         * search system later.
                         */

                    }

                }

            }
        );

    }


    /* =====================================================
       AUTO DISMISS ALERTS
    ===================================================== */

    const alerts =
        document.querySelectorAll(
            ".alert"
        );


    alerts.forEach(function (alert) {

        setTimeout(function () {

            if (
                typeof bootstrap !==
                "undefined"
            ) {

                const instance =
                    bootstrap.Alert.getOrCreateInstance(
                        alert
                    );

                instance.close();

            }

        }, 5000);

    });



    /* =====================================================
       REGISTRATION PAGE
    ===================================================== */

    initializeRegistrationPage();


});



/* =========================================================
   REGISTRATION PAGE FUNCTIONS
========================================================= */

function initializeRegistrationPage() {


    /*
     * Only run registration-specific
     * functionality when the page
     * contains a registration form.
     */

    const registerForm =
        document.querySelector(
            ".register-card form"
        );


    if (!registerForm) {
        return;
    }



    /* =====================================================
       ROLE SELECTION
    ===================================================== */

    const roleOptions =
        document.querySelectorAll(
            ".role-option"
        );


    roleOptions.forEach(function (option) {

        const radio =
            option.querySelector(
                "input[type='radio']"
            );


        if (!radio) {
            return;
        }


        function updateSelectedRole() {

            roleOptions.forEach(
                function (item) {

                    item.classList.remove(
                        "selected"
                    );

                }
            );


            if (radio.checked) {

                option.classList.add(
                    "selected"
                );

            }

        }


        radio.addEventListener(
            "change",
            updateSelectedRole
        );


        option.addEventListener(
            "click",
            function (event) {

                /*
                 * Avoid triggering
                 * the event twice when
                 * clicking directly
                 * on the radio button.
                 */

                if (
                    event.target !== radio
                ) {

                    radio.checked = true;

                }

                updateSelectedRole();

            }
        );


        updateSelectedRole();

    });



    /* =====================================================
       DJANGO FORM FIELD STYLING
    ===================================================== */

    const formControls =
        registerForm.querySelectorAll(
            "input:not([type='radio']):not([type='checkbox']):not([type='hidden']), select, textarea"
        );


    formControls.forEach(
        function (field) {

            field.classList.add(
                "form-control"
            );


            /*
             * Useful browser
             * autocomplete settings.
             */

            if (
                field.name === "email"
            ) {

                field.setAttribute(
                    "autocomplete",
                    "email"
                );

            }


            if (
                field.name === "username"
            ) {

                field.setAttribute(
                    "autocomplete",
                    "username"
                );

            }


            if (
                field.name === "first_name"
            ) {

                field.setAttribute(
                    "autocomplete",
                    "given-name"
                );

            }


            if (
                field.name === "last_name"
            ) {

                field.setAttribute(
                    "autocomplete",
                    "family-name"
                );

            }


            if (
                field.name === "password1"
            ) {

                field.setAttribute(
                    "autocomplete",
                    "new-password"
                );

            }


            if (
                field.name === "password2"
            ) {

                field.setAttribute(
                    "autocomplete",
                    "new-password"
                );

            }

        }
    );



    /* =====================================================
       PASSWORD SHOW / HIDE
    ===================================================== */

    const passwordFields =
        registerForm.querySelectorAll(
            "input[type='password']"
        );


    passwordFields.forEach(
        function (field) {

            /*
             * Don't create a second
             * toggle if one already exists.
             */

            const existingToggle =
                field.parentElement.querySelector(
                    ".password-toggle"
                );


            if (existingToggle) {
                return;
            }


            /*
             * Create input group
             * if Django didn't provide one.
             */

            let wrapper =
                field.closest(
                    ".input-group"
                );


            if (!wrapper) {

                wrapper =
                    document.createElement(
                        "div"
                    );

                wrapper.className =
                    "input-group";


                field.parentNode.insertBefore(
                    wrapper,
                    field
                );


                wrapper.appendChild(
                    field
                );

            }


            const button =
                document.createElement(
                    "button"
                );


            button.type = "button";

            button.className =
                "password-toggle input-group-text";


            button.innerHTML =
                '<i class="bi bi-eye"></i>';


            button.setAttribute(
                "aria-label",
                "Show password"
            );


            wrapper.appendChild(
                button
            );


            button.addEventListener(
                "click",
                function () {

                    if (
                        field.type ===
                        "password"
                    ) {

                        field.type =
                            "text";


                        button.innerHTML =
                            '<i class="bi bi-eye-slash"></i>';


                        button.setAttribute(
                            "aria-label",
                            "Hide password"
                        );

                    }

                    else {

                        field.type =
                            "password";


                        button.innerHTML =
                            '<i class="bi bi-eye"></i>';


                        button.setAttribute(
                            "aria-label",
                            "Show password"
                        );

                    }

                }
            );

        }
    );



    /* =====================================================
       PASSWORD STRENGTH
    ===================================================== */

    const password =
        registerForm.querySelector(
            "input[name='password1']"
        );


    if (password) {

        /*
         * Don't create another
         * strength indicator if
         * one already exists.
         */

        if (
            !registerForm.querySelector(
                ".password-strength"
            )
        ) {

            const strengthContainer =
                document.createElement(
                    "div"
                );


            strengthContainer.className =
                "password-strength-wrapper";


            strengthContainer.innerHTML = `

                <div class="password-strength">

                    <div
                        class="password-strength-bar"
                    ></div>

                </div>

                <span
                    class="password-strength-text"
                >
                    Use a strong password.
                </span>

            `;


            /*
             * Put the indicator
             * directly after the
             * password input group.
             */

            const inputGroup =
                password.closest(
                    ".input-group"
                );


            if (inputGroup) {

                inputGroup.parentNode.insertBefore(
                    strengthContainer,
                    inputGroup.nextSibling
                );

            }

            else {

                password.parentNode.appendChild(
                    strengthContainer
                );

            }

        }


        const strengthBar =
            registerForm.querySelector(
                ".password-strength-bar"
            );


        const strengthText =
            registerForm.querySelector(
                ".password-strength-text"
            );


        password.addEventListener(
            "input",
            function () {

                const value =
                    password.value;


                let score = 0;


                if (
                    value.length >= 8
                ) {

                    score++;

                }


                if (
                    value.length >= 12
                ) {

                    score++;

                }


                if (
                    /[A-Z]/.test(value)
                ) {

                    score++;

                }


                if (
                    /[a-z]/.test(value)
                ) {

                    score++;

                }


                if (
                    /[0-9]/.test(value)
                ) {

                    score++;

                }


                if (
                    /[^A-Za-z0-9]/.test(value)
                ) {

                    score++;

                }


                if (!value) {

                    strengthBar.style.width =
                        "0%";

                    strengthText.textContent =
                        "Use a strong password.";

                    return;

                }


                if (score <= 2) {

                    strengthBar.style.width =
                        "30%";

                    strengthText.textContent =
                        "Weak password";

                }

                else if (score <= 4) {

                    strengthBar.style.width =
                        "65%";

                    strengthText.textContent =
                        "Good password";

                }

                else {

                    strengthBar.style.width =
                        "100%";

                    strengthText.textContent =
                        "Strong password";

                }

            }
        );

    }



    /* =====================================================
       PASSWORD MATCH CHECK
    ===================================================== */

    const confirmPassword =
        registerForm.querySelector(
            "input[name='password2']"
        );


    if (
        password &&
        confirmPassword
    ) {

        const matchMessage =
            document.createElement(
                "small"
            );


        matchMessage.className =
            "password-match-message";


        confirmPassword.parentElement.appendChild(
            matchMessage
        );


        function checkPasswords() {

            if (
                !confirmPassword.value
            ) {

                matchMessage.textContent =
                    "";

                return;

            }


            if (
                password.value ===
                confirmPassword.value
            ) {

                matchMessage.textContent =
                    "Passwords match ✓";

                matchMessage.className =
                    "password-match-message text-success small";

            }

            else {

                matchMessage.textContent =
                    "Passwords do not match.";

                matchMessage.className =
                    "password-match-message text-danger small";

            }

        }


        password.addEventListener(
            "input",
            checkPasswords
        );


        confirmPassword.addEventListener(
            "input",
            checkPasswords
        );

    }



    /* =====================================================
       REGISTER BUTTON
    ===================================================== */

    const registerButton =
        registerForm.querySelector(
            ".register-button"
        );


    if (registerButton) {

        registerForm.addEventListener(
            "submit",
            function () {

                /*
                 * Only change the button
                 * after browser validation
                 * has passed.
                 */

                if (
                    !registerForm.checkValidity()
                ) {

                    return;

                }


                registerButton.disabled =
                    true;


                registerButton.innerHTML = `

                    <span
                        class="spinner-border spinner-border-sm me-2"
                        role="status"
                        aria-hidden="true"
                    ></span>

                    Creating your account...

                `;

            }
        );

    }



    /* =====================================================
       SMOOTH FIELD FOCUS
    ===================================================== */

    const inputs =
        registerForm.querySelectorAll(
            ".form-control"
        );


    inputs.forEach(
        function (input) {

            input.addEventListener(
                "focus",
                function () {

                    const group =
                        input.closest(
                            ".form-group"
                        );


                    if (group) {

                        group.classList.add(
                            "focused"
                        );

                    }

                }
            );


            input.addEventListener(
                "blur",
                function () {

                    const group =
                        input.closest(
                            ".form-group"
                        );


                    if (group) {

                        group.classList.remove(
                            "focused"
                        );

                    }

                }
            );

        }
    );

}



/* =========================================================
   GLOBAL WEBRTC CALLING
========================================================= */

let localStream = null;
let callSocket = null;
let currentCallId = null;
let currentCallType = null;
let callTimerInterval = null;
let callConnectedAt = null;
let isCallStarting = false;


/*
 * =========================================================
 * GLOBAL CALL STATE
 * =========================================================
 *
 * This represents the actual application-level state
 * of the current call.
 *
 * It is different from WebRTC peer connections.
 * =========================================================
 */

const globalCallState = {

    callId: null,

    callType: null,

    status: null,

    participants: {},

    joinedParticipants: {},

    ringingParticipants: {},

    invitedParticipants: {},

    rejectedParticipants: {},

    leftParticipants: {}
};


/*
 * =========================================================
 * WEBRTC STATE
 * =========================================================
 */

const peerConnections = {};

const pendingIceCandidates = {};

const callParticipants = {};


/*
 * =========================================================
 * SYNCHRONIZE GLOBAL CALL STATE
 * =========================================================
 */

function syncGlobalCallState(callData) {

    if (!callData) {
        return;
    }


    /*
     * -----------------------------------------------------
     * BASIC CALL INFORMATION
     * -----------------------------------------------------
     */

    globalCallState.callId =
        Number(callData.id || 0);

    globalCallState.callType =
        callData.call_type || null;

    globalCallState.status =
        callData.status || null;


    /*
     * -----------------------------------------------------
     * RESET PARTICIPANT STATE
     * -----------------------------------------------------
     */

    globalCallState.participants = {};

    globalCallState.joinedParticipants = {};

    globalCallState.ringingParticipants = {};

    globalCallState.invitedParticipants = {};

    globalCallState.rejectedParticipants = {};

    globalCallState.leftParticipants = {};


    /*
     * -----------------------------------------------------
     * PROCESS PARTICIPANTS
     * -----------------------------------------------------
     */

    const participants =
        callData.participants || [];


    participants.forEach(function (participant) {

        if (!participant.user) {
            return;
        }


        const userId =
            Number(participant.user.id);


        const participantData = {

            id: userId,

            username:
                participant.user.username ||
                "Participant",

            first_name:
                participant.user.first_name ||
                "",

            last_name:
                participant.user.last_name ||
                "",

            status:
                participant.status,

            joined_at:
                participant.joined_at || null,

            left_at:
                participant.left_at || null
        };


        /*
         * Store complete participant information.
         */

        globalCallState.participants[userId] =
            participantData;


        /*
         * -------------------------------------------------
         * SORT BY ACTUAL DATABASE STATUS
         * -------------------------------------------------
         */

        if (
            participant.status ===
            "JOINED"
        ) {

            globalCallState.joinedParticipants[
                userId
            ] = participantData;

        }


        else if (
            participant.status ===
            "RINGING"
        ) {

            globalCallState.ringingParticipants[
                userId
            ] = participantData;

        }


        else if (
            participant.status ===
            "INVITED"
        ) {

            globalCallState.invitedParticipants[
                userId
            ] = participantData;

        }


        else if (
            participant.status ===
            "REJECTED"
        ) {

            globalCallState.rejectedParticipants[
                userId
            ] = participantData;

        }


        else if (
            participant.status ===
            "LEFT"
        ) {

            globalCallState.leftParticipants[
                userId
            ] = participantData;
        }

    });


    /*
     * -----------------------------------------------------
     * DEBUG INFORMATION
     * -----------------------------------------------------
     */

    console.log(
        "GLOBAL CALL STATE:",
        globalCallState
    );

    console.log(
        "Joined participants:",
        Object.keys(
            globalCallState.joinedParticipants
        )
    );

    console.log(
        "Ringing participants:",
        Object.keys(
            globalCallState.ringingParticipants
        )
    );

    console.log(
        "Invited participants:",
        Object.keys(
            globalCallState.invitedParticipants
        )
    );

}

/*
 * =========================================================
 * GET ACTIVE CALL PARTICIPANTS
 * =========================================================
 */

function getActiveCallParticipants() {

    return Object.values(
        globalCallState.joinedParticipants
    );
}

/*
 * =========================================================
 * CHECK WHETHER CALL HAS ACTIVE PARTICIPANTS
 * =========================================================
 */

function hasActiveCallParticipants() {

    return (
        Object.keys(
            globalCallState.joinedParticipants
        ).length > 0
    );
}

const rtcConfiguration = {
    iceServers: [
        {
            urls: "stun:stun.l.google.com:19302"
        }
    ]
};

const currentUserId =
    Number(window.awinlinkCurrentUserId || 0);


/* =========================================================
   CALL TIMEOUTS
========================================================= */

let incomingCallId = null;
let incomingCallTimeout = null;
let outgoingCallTimeout = null;


/* =========================================================
   CSRF
========================================================= */

function getCookie(name) {

    let cookieValue = null;

    if (document.cookie && document.cookie !== "") {

        const cookies =
            document.cookie.split(";");

        for (let i = 0; i < cookies.length; i++) {

            const cookie =
                cookies[i].trim();

            if (
                cookie.substring(
                    0,
                    name.length + 1
                ) === name + "="
            ) {

                cookieValue =
                    decodeURIComponent(
                        cookie.substring(
                            name.length + 1
                        )
                    );

                break;
            }
        }
    }

    return cookieValue;
}


/* =========================================================
   CLEAR TIMEOUTS
========================================================= */

function clearIncomingCallTimeout() {

    if (incomingCallTimeout) {

        clearInterval(
            incomingCallTimeout
        );

        incomingCallTimeout = null;
    }
}


function clearOutgoingCallTimeout() {

    if (outgoingCallTimeout) {

        clearTimeout(
            outgoingCallTimeout
        );

        outgoingCallTimeout = null;
    }
}


/* =========================================================
   SEND WEBRTC SIGNAL
========================================================= */

function sendCallSignal(data) {

    if (
        !callSocket ||
        callSocket.readyState !== WebSocket.OPEN
    ) {

        console.warn(
            "Cannot send call signal. Socket is not open."
        );

        return;
    }

    callSocket.send(
        JSON.stringify(data)
    );
}


/* =========================================================
   CREATE PEER CONNECTION
========================================================= */

async function createPeerConnection(
    remoteUserId,
    createOffer = false
) {

    remoteUserId =
        Number(remoteUserId);


    if (peerConnections[remoteUserId]) {

        return peerConnections[remoteUserId];

    }


    console.log(
        "Creating peer connection with:",
        remoteUserId
    );


    const peerConnection =
        new RTCPeerConnection(
            rtcConfiguration
        );


    peerConnections[remoteUserId] =
        peerConnection;


    /*
     * Add local media.
     */

    if (localStream) {

        localStream
            .getTracks()
            .forEach(function (track) {

                peerConnection.addTrack(
                    track,
                    localStream
                );

            });

    }


    /*
     * Remote media.
     */

    peerConnection.ontrack =
        function (event) {

            console.log(
                "Remote track received from:",
                remoteUserId
            );

            if (event.streams.length > 0) {

                addRemoteVideo(
                    remoteUserId,
                    event.streams[0]
                );

            }

        };


    /*
     * ICE candidates.
     */

    peerConnection.onicecandidate =
        function (event) {

            if (event.candidate) {

                sendCallSignal({

                    type: "ice-candidate",

                    target_id:
                        remoteUserId,

                    candidate:
                        event.candidate

                });

            }

        };


    /*
     * Connection state.
     */

    peerConnection.onconnectionstatechange =
        function () {

            console.log(
                "Connection state:",
                remoteUserId,
                peerConnection.connectionState
            );

            if (peerConnection.connectionState === "connected") {
                setCallStatus("Connected");
                startCallTimer();
            } else if (peerConnection.connectionState === "connecting") {
                setCallStatus("Connecting audio and video…");
            } else if (peerConnection.connectionState === "disconnected") {
                setCallStatus("Reconnecting…");
            }


            if (
                peerConnection.connectionState ===
                "failed"
            ) {

                removePeerConnection(
                    remoteUserId
                );

                if (!Object.keys(peerConnections).length) {
                    setCallStatus("Connection failed. Check your network and try again.");
                }

            }

        };


    /*
     * Create offer when required.
     */

    if (createOffer) {

        const offer =
            await peerConnection.createOffer();

        await peerConnection.setLocalDescription(
            offer
        );


        sendCallSignal({

            type: "offer",

            target_id:
                remoteUserId,

            offer:
                offer

        });


        console.log(
            "Offer sent to:",
            remoteUserId
        );

    }


    return peerConnection;
}


/* =========================================================
   PROCESS PENDING ICE
========================================================= */

async function processPendingIceCandidates(
    remoteUserId
) {

    remoteUserId =
        Number(remoteUserId);


    const candidates =
        pendingIceCandidates[remoteUserId];


    if (!candidates) {

        return;

    }


    const peerConnection =
        peerConnections[remoteUserId];


    if (!peerConnection) {

        return;

    }


    for (
        const candidate of candidates
    ) {

        try {

            await peerConnection.addIceCandidate(
                candidate
            );

        } catch (error) {

            console.error(
                "Unable to add queued ICE candidate:",
                error
            );

        }

    }


    delete pendingIceCandidates[
        remoteUserId
    ];

}


/* =========================================================
   HANDLE WEBRTC SIGNAL
========================================================= */

async function handleCallSignal(data) {

    console.log(
        "Received WebRTC message:",
        data
    );


    /*
 * Call ended for everyone.
 */
// =====================================================
// CALL ENDED FOR EVERYONE
// =====================================================

if (data.type === "call_ended") {

    console.log(
        "Call ended by:",
        data.ended_by_username || data.ended_by
    );

    clearOutgoingCallTimeout();
    clearIncomingCallTimeout();

    // Prevent another /end/ request
    currentCallId = null;

    // Close all peer connections
    cleanupWebRTC();

    return;
}

    /*
     * Connection established.
     */

    if (data.type === "connection") {

        console.log(
            "Call WebSocket connection confirmed."
        );

        return;

    }


    /*
     * Participant joined.
     */

    if (
        data.type ===
        "participant_joined"
    ) {

        const userId =
            Number(data.user_id);


        if (
            userId === currentUserId
        ) {

            return;

        }


        callParticipants[userId] = {

            id:
                userId,

            username:
                data.username ||
                "Participant"

        };

        setCallStatus("Connecting audio and video…");


        console.log(
            "Participant joined:",
            userId,
            data.username
        );


        clearOutgoingCallTimeout();


        /*
         * The existing participant
         * creates the offer.
         */

        await createPeerConnection(
            userId,
            true
        );


        return;

    }


    /*
     * Participant left.
     */

    if (
        data.type ===
        "participant_left"
    ) {

        const userId =
            Number(data.user_id);


        console.log(
            "Participant left:",
            userId
        );


        removePeerConnection(
            userId
        );


        delete callParticipants[
            userId
        ];


        return;

    }


    /*
     * Participant rejected.
     */

    if (
        data.type ===
        "participant_rejected"
    ) {

        const userId =
            Number(data.user_id);


        removePeerConnection(
            userId
        );


        delete callParticipants[
            userId
        ];


        return;

    }


    /*
     * Ignore signals intended
     * for another user.
     */

    if (
        data.target_id &&
        Number(data.target_id) !==
        currentUserId
    ) {

        return;

    }


    /* =====================================================
       OFFER
    ===================================================== */

    if (data.type === "offer") {

        const remoteUserId =
            Number(data.sender_id);


        console.log(
            "Received offer from:",
            remoteUserId
        );


        const peerConnection =
            await createPeerConnection(
                remoteUserId,
                false
            );


        await peerConnection.setRemoteDescription(
            new RTCSessionDescription(
                data.offer
            )
        );


        await processPendingIceCandidates(
            remoteUserId
        );


        const answer =
            await peerConnection.createAnswer();


        await peerConnection.setLocalDescription(
            answer
        );


        sendCallSignal({

            type:
                "answer",

            target_id:
                remoteUserId,

            answer:
                answer

        });


        console.log(
            "Answer sent to:",
            remoteUserId
        );


        return;

    }


    /* =====================================================
       ANSWER
    ===================================================== */

    if (data.type === "answer") {

        const remoteUserId =
            Number(data.sender_id);


        console.log(
            "Received answer from:",
            remoteUserId
        );


        const peerConnection =
            peerConnections[
                remoteUserId
            ];


        if (!peerConnection) {

            console.warn(
                "No peer connection for answer:",
                remoteUserId
            );

            return;

        }


        await peerConnection.setRemoteDescription(
            new RTCSessionDescription(
                data.answer
            )
        );


        await processPendingIceCandidates(
            remoteUserId
        );


        return;

    }


    /* =====================================================
       ICE CANDIDATE
    ===================================================== */

    if (
        data.type ===
        "ice-candidate"
    ) {

        const remoteUserId =
            Number(data.sender_id);


        const candidate =
            new RTCIceCandidate(
                data.candidate
            );


        const peerConnection =
            peerConnections[
                remoteUserId
            ];


        /*
         * Queue ICE until the
         * remote description exists.
         */

        if (
            !peerConnection ||
            !peerConnection.remoteDescription
        ) {

            if (
                !pendingIceCandidates[
                    remoteUserId
                ]
            ) {

                pendingIceCandidates[
                    remoteUserId
                ] = [];

            }


            pendingIceCandidates[
                remoteUserId
            ].push(candidate);


            return;

        }


        try {

            await peerConnection.addIceCandidate(
                candidate
            );

        } catch (error) {

            console.error(
                "Unable to add ICE candidate:",
                error
            );

        }

    }

}


/* =========================================================
   CONNECT CALL WEBSOCKET
========================================================= */

function connectCallSocket(callId) {

    return new Promise(
        function (resolve, reject) {

            currentCallId =
                Number(callId);


            const protocol =
                location.protocol === "https:"
                    ? "wss"
                    : "ws";


            const socketUrl =
                `${protocol}://${window.location.host}/ws/calls/${currentCallId}/`;


            console.log(
                "Connecting to call WebSocket:",
                socketUrl
            );


            callSocket =
                new WebSocket(socketUrl);


            callSocket.onopen =
                function () {

                    console.log(
                        "Call WebSocket connected."
                    );

                    resolve();

                };


            callSocket.onmessage =
                async function (event) {

                    try {

                        const data =
                            JSON.parse(
                                event.data
                            );

                        await handleCallSignal(
                            data
                        );

                    } catch (error) {

                        console.error(
                            "Call WebSocket message error:",
                            error
                        );

                    }

                };


            callSocket.onerror =
                function (error) {

                    console.error(
                        "Call WebSocket error:",
                        error
                    );

                    reject(error);

                };


            callSocket.onclose =
                function () {

                    console.log(
                        "Call WebSocket disconnected."
                    );

                };

        }
    );

}


/* =========================================================
   START CALL
========================================================= */

async function startCall(
    callType,
    conversationId
) {

    if (isCallStarting || currentCallId) {
        return;
    }

    isCallStarting = true;

    try {

        if (!conversationId) {

            throw new Error(
                "Conversation ID is required."
            );

        }


        /*
         * Get microphone/camera.
         */

        localStream =
            await navigator.mediaDevices.getUserMedia({

                audio: true,

                video:
                    callType === "VIDEO"

            });


        console.log(
            `${callType} call media stream started.`
        );


        /*
         * Create call.
         */

        const response =
            await fetch(
                `/api/messaging/conversations/${conversationId}/calls/start/`,
                {

                    method: "POST",

                    headers: {

                        "Content-Type":
                            "application/json",

                        "X-CSRFToken":
                            getCookie("csrftoken")

                    },

                    credentials:
                        "same-origin",

                    body:
                        JSON.stringify({

                            call_type:
                                callType

                        })

                }
            );


        if (!response.ok) {

            const errorData =
                await response.json()
                    .catch(
                        () => ({})
                    );


            throw new Error(
                errorData.detail ||
                "Unable to start call."
            );

        }


        const callData =
            await response.json();


        console.log(
            "Awinlink call created:",
            callData
        );

        syncGlobalCallState(callData);


        currentCallId =
            Number(callData.id);
        currentCallType = callType;


        /*
         * Save participants.
         */

        if (
            callData.participants
        ) {

            callData.participants.forEach(
                function (participant) {

                    const user =
                        participant.user;

                    if (
                        user &&
                        Number(user.id) !==
                        currentUserId
                    ) {

                        callParticipants[
                            Number(user.id)
                        ] = user;

                    }

                }
            );

        }


        /*
         * Show call UI.
         */

        showCallInterface(
            callType,
            callData.participants || [],
            "Calling…"
        );


        /*
         * Attach local video.
         */

        const localVideo =
            document.getElementById(
                "localVideo"
            );


        if (localVideo) {

            localVideo.srcObject =
                localStream;

        }


        /*
         * Give receiver 30 seconds
         * to answer.
         */

        clearOutgoingCallTimeout();


        const thisCallId =
            currentCallId;


        outgoingCallTimeout =
            setTimeout(
                async function () {

                    if (
                        currentCallId !==
                        thisCallId
                    ) {

                        return;

                    }


                    console.log(
                        "Outgoing call timed out."
                    );


                    currentCallId =
                        null;


                    try {

                        await fetch(
                            `/api/messaging/calls/${thisCallId}/end/`,
                            {

                                method: "POST",

                                headers: {

                                    "Content-Type":
                                        "application/json",

                                    "X-CSRFToken":
                                        getCookie(
                                            "csrftoken"
                                        )

                                },

                                credentials:
                                    "same-origin",

                                body:
                                    JSON.stringify({

                                        end_for_everyone:
                                            true

                                    })

                            }
                        );

                    } catch (error) {

                        console.error(
                            "Unable to end timed-out call:",
                            error
                        );

                    }


                    cleanupWebRTC();

                },
                30000
            );


        /*
         * Connect call WebSocket.
         */

        await connectCallSocket(
            currentCallId
        );


        console.log(
            "Waiting for other participants to join..."
        );


    } catch (error) {

        console.error(
            "Unable to start call:",
            error
        );


        if (currentCallId) {
            await endWebRTCCall();
        } else {
            cleanupWebRTC();
        }


        alert(
            error.message ||
            "Unable to start call."
        );

    } finally {
        isCallStarting = false;

    }

}


/* =========================================================
   PUBLIC CALL FUNCTIONS
========================================================= */

window.startVoiceCall =
    function (conversationId) {

        startCall(
            "VOICE",
            conversationId
        );

    };


window.startVideoCall =
    function (conversationId) {

        startCall(
            "VIDEO",
            conversationId
        );

    };


/* =========================================================
   SHOW CALL INTERFACE
========================================================= */

function showCallInterface(
    callType,
    participants = [],
    initialStatus = "Connecting…"
) {
    currentCallType = callType;

    let container = document.getElementById("awinlinkCallContainer");
    if (!container) {
        container = document.createElement("div");
        container.id = "awinlinkCallContainer";
        container.className = "awinlink-call-overlay";
        container.setAttribute("role", "dialog");
        container.setAttribute("aria-modal", "true");
        container.setAttribute("aria-label", "Active call");
        container.innerHTML = `
            <section class="awinlink-call-panel">
                <header class="awinlink-call-header">
                    <div class="awinlink-call-heading">
                        <span class="call-live-indicator" aria-hidden="true"></span>
                        <div>
                            <p class="call-eyebrow" id="awinlinkCallTitle">Video call</p>
                            <h1 id="callRemoteName">Connecting…</h1>
                        </div>
                    </div>
                    <div class="call-state-group">
                        <span id="awinlinkCallStatus" class="call-status">Connecting…</span>
                        <span id="awinlinkCallTimer" class="call-duration">00:00</span>
                    </div>
                </header>

                <main class="awinlink-call-stage">
                    <div id="callVoiceStage" class="call-voice-stage">
                        <div id="callRemoteAvatar" class="call-avatar" aria-hidden="true">?</div>
                        <p class="call-voice-caption">Your call is ready when they join</p>
                    </div>
                    <div id="remoteVideos" class="call-video-grid" aria-live="polite"></div>
                    <div id="callLocalTile" class="call-local-tile">
                        <video id="localVideo" autoplay muted playsinline></video>
                        <span class="call-tile-label">You</span>
                    </div>
                </main>

                <footer class="awinlink-call-footer">
                    <div class="call-controls" aria-label="Call controls">
                        <button type="button" id="toggleCallMicrophone" class="call-control-button" aria-label="Mute microphone" aria-pressed="false" title="Mute microphone">
                            <i class="bi bi-mic-fill" aria-hidden="true"></i>
                            <span>Mute</span>
                        </button>
                        <button type="button" id="toggleCallCamera" class="call-control-button" aria-label="Turn camera off" aria-pressed="false" title="Turn camera off">
                            <i class="bi bi-camera-video-fill" aria-hidden="true"></i>
                            <span>Camera</span>
                        </button>
                        <button type="button" id="endAwinlinkCall" class="call-control-button call-end-button" aria-label="End call" title="End call">
                            <i class="bi bi-telephone-x-fill" aria-hidden="true"></i>
                            <span>End</span>
                        </button>
                    </div>
                </footer>
            </section>
        `;
        document.body.appendChild(container);

        const microphoneButton = document.getElementById("toggleCallMicrophone");
        microphoneButton.addEventListener("click", function () {
            const tracks = localStream ? localStream.getAudioTracks() : [];
            const shouldMute = tracks.some(function (track) { return track.enabled; });
            tracks.forEach(function (track) { track.enabled = !shouldMute; });
            microphoneButton.classList.toggle("is-muted", shouldMute);
            microphoneButton.setAttribute("aria-pressed", String(shouldMute));
            microphoneButton.setAttribute("aria-label", shouldMute ? "Unmute microphone" : "Mute microphone");
            microphoneButton.title = shouldMute ? "Unmute microphone" : "Mute microphone";
            microphoneButton.querySelector("i").className = shouldMute ? "bi bi-mic-mute-fill" : "bi bi-mic-fill";
            microphoneButton.querySelector("span").textContent = shouldMute ? "Unmute" : "Mute";
        });

        const cameraButton = document.getElementById("toggleCallCamera");
        cameraButton.addEventListener("click", function () {
            const tracks = localStream ? localStream.getVideoTracks() : [];
            const shouldDisable = tracks.some(function (track) { return track.enabled; });
            tracks.forEach(function (track) { track.enabled = !shouldDisable; });
            cameraButton.classList.toggle("is-muted", shouldDisable);
            cameraButton.setAttribute("aria-pressed", String(shouldDisable));
            cameraButton.setAttribute("aria-label", shouldDisable ? "Turn camera on" : "Turn camera off");
            cameraButton.title = shouldDisable ? "Turn camera on" : "Turn camera off";
            cameraButton.querySelector("i").className = shouldDisable ? "bi bi-camera-video-off-fill" : "bi bi-camera-video-fill";
            cameraButton.querySelector("span").textContent = shouldDisable ? "Camera on" : "Camera";
        });

        document.getElementById("endAwinlinkCall").addEventListener("click", endWebRTCCall);
    }

    const isVideoCall = callType === "VIDEO";
    container.classList.toggle("is-video-call", isVideoCall);
    document.getElementById("awinlinkCallTitle").textContent = isVideoCall ? "Video call" : "Voice call";
    setCallStatus(initialStatus);

    const remoteUsers = participants
        .map(function (participant) { return participant.user; })
        .filter(function (user) { return user && Number(user.id) !== currentUserId; });

    remoteUsers.forEach(function (user) {
        callParticipants[Number(user.id)] = user;
    });

    const remoteName = remoteUsers.length > 1
        ? `${remoteUsers.length} participants`
        : remoteUsers.length === 1
            ? [remoteUsers[0].first_name, remoteUsers[0].last_name].filter(Boolean).join(" ") || remoteUsers[0].username || "Contact"
            : "Waiting for participant";

    const nameElement = document.getElementById("callRemoteName");
    const avatarElement = document.getElementById("callRemoteAvatar");
    nameElement.textContent = remoteName;
    avatarElement.textContent = remoteName === "Waiting for participant"
        ? "…"
        : remoteName.trim().charAt(0).toUpperCase();

    document.getElementById("callVoiceStage").hidden = isVideoCall;
    document.getElementById("remoteVideos").hidden = !isVideoCall;
    document.getElementById("callLocalTile").hidden = !isVideoCall;
    document.getElementById("toggleCallCamera").hidden = !isVideoCall;
    document.getElementById("localVideo").srcObject = localStream;
}


/* =========================================================
   ADD REMOTE VIDEO
========================================================= */

function addRemoteVideo(
    remoteUserId,
    stream
) {
    remoteUserId = Number(remoteUserId);

    const remoteVideos = document.getElementById("remoteVideos");
    if (!remoteVideos) return;

    const user = callParticipants[remoteUserId] || {};
    const remoteName = [user.first_name, user.last_name].filter(Boolean).join(" ")
        || user.username
        || `Participant ${remoteUserId}`;

    if (currentCallType === "VOICE") {
        let audio = document.getElementById(`remote-audio-${remoteUserId}`);
        if (!audio) {
            audio = document.createElement("audio");
            audio.id = `remote-audio-${remoteUserId}`;
            audio.className = "call-remote-audio";
            audio.autoplay = true;
            audio.playsInline = true;
            remoteVideos.appendChild(audio);
        }
        audio.srcObject = stream;
        audio.play().catch(function (error) {
            console.warn("Remote audio playback was blocked:", error);
            setCallStatus("Tap the page to enable call audio");
        });
        return;
    }

    let wrapper = document.getElementById(`remote-wrapper-${remoteUserId}`);
    if (!wrapper) {
        wrapper = document.createElement("div");
        wrapper.id = `remote-wrapper-${remoteUserId}`;
        wrapper.className = "call-video-tile";

        const video = document.createElement("video");
        video.id = `remote-video-${remoteUserId}`;
        video.autoplay = true;
        video.playsInline = true;
        video.className = "call-remote-video";
        wrapper.appendChild(video);

        const name = document.createElement("span");
        name.className = "call-video-name";
        name.textContent = remoteName;
        wrapper.appendChild(name);

        remoteVideos.appendChild(wrapper);
    }

    const video = wrapper.querySelector("video");
    if (video && video.srcObject !== stream) {
        video.srcObject = stream;
    }
}


/* =========================================================
   REMOVE PEER CONNECTION
========================================================= */

function removePeerConnection(
    userId
) {

    userId =
        Number(userId);


    const peerConnection =
        peerConnections[userId];


    if (peerConnection) {

        try {

            peerConnection.close();

        } catch (error) {

            console.warn(
                "Unable to close peer connection:",
                error
            );

        }

        delete peerConnections[
            userId
        ];

    }


    delete pendingIceCandidates[
        userId
    ];


    const wrapper =
        document.getElementById(
            `remote-wrapper-${userId}`
        );


    if (wrapper) {

        wrapper.remove();

    }

    const remoteAudio = document.getElementById(`remote-audio-${userId}`);
    if (remoteAudio) remoteAudio.remove();

}


/* =========================================================
   CLEANUP WEBRTC
========================================================= */

function cleanupWebRTC() {

    console.log(
        "Cleaning up WebRTC..."
    );


    clearIncomingCallTimeout();
    clearOutgoingCallTimeout();
    stopCallTimer();


    Object.keys(
        peerConnections
    ).forEach(
        function (userId) {

            try {

                peerConnections[
                    userId
                ].close();

            } catch (error) {

                console.warn(error);

            }

            delete peerConnections[
                userId
            ];

        }
    );


    Object.keys(
        pendingIceCandidates
    ).forEach(
        function (userId) {

            delete pendingIceCandidates[
                userId
            ];

        }
    );


    if (callSocket) {

        try {

            callSocket.close();

        } catch (error) {

            console.warn(error);

        }

        callSocket = null;

    }


    if (localStream) {

        localStream
            .getTracks()
            .forEach(
                function (track) {

                    track.stop();

                }
            );

        localStream = null;

    }


    Object.keys(
        callParticipants
    ).forEach(
        function (userId) {

            delete callParticipants[
                userId
            ];

        }
    );


    currentCallId =
        null;
    currentCallType = null;


    const container =
        document.getElementById(
            "awinlinkCallContainer"
        );


    if (container) {

        container.remove();

    }

}


/* =========================================================
   END WEBRTC CALL
========================================================= */
async function endWebRTCCall() {

    // =====================================================
    // STOP CALL TIMEOUTS
    // =====================================================

    clearOutgoingCallTimeout();
    clearIncomingCallTimeout();


    // =====================================================
    // NO ACTIVE CALL
    // =====================================================

    if (!currentCallId) {

        cleanupWebRTC();

        return;
    }


    // =====================================================
    // SAVE CALL ID
    // =====================================================

    const callId =
        currentCallId;


    // =====================================================
    // CLEAR IMMEDIATELY
    //
    // Prevents duplicate /end/ requests.
    // =====================================================

    currentCallId = null;


    try {

        const response =
            await fetch(
                `/api/messaging/calls/${callId}/end/`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json",

                        "X-CSRFToken":
                            getCookie(
                                "csrftoken"
                            )
                    },

                    credentials:
                        "same-origin",

                    body:
                        JSON.stringify({
                            end_for_everyone:
                                true
                        })
                }
            );


        const data =
            await response
                .json()
                .catch(
                    () => ({})
                );


        if (!response.ok) {

            console.warn(
                "Call may already be ended:",
                data
            );

        } else {

            console.log(
                "Call ended for everyone:",
                data
            );
        }


    } catch (error) {

        console.error(
            "Error ending call:",
            error
        );

    } finally {

        // =================================================
        // CLEAN THIS USER'S WEBRTC CONNECTION
        // =================================================

        cleanupWebRTC();
    }
}

/* =========================================================
   GLOBAL INCOMING CALL UI
========================================================= */

function showIncomingCall(call) {

    if (!call || !call.call_id) {

        return;

    }


    if (incomingCallId) {

        return;

    }


    if (
        currentCallId || isCallStarting
    ) {

        return;

    }


    incomingCallId =
        Number(call.call_id);


    const caller =
        call.caller || {};


    const callerName =
        caller.first_name ||
        caller.username ||
        "Someone";


    const callType =
        call.call_type === "VIDEO"
            ? "video"
            : "voice";


    const overlay =
        document.createElement(
            "div"
        );


    overlay.id =
        "globalIncomingCallOverlay";


    overlay.className =
        "incoming-call-overlay";


    overlay.innerHTML = `

        <div class="incoming-call-window">

            <div class="incoming-call-icon">

                ${
                    call.call_type === "VIDEO"
                    ? "📹"
                    : "📞"
                }

            </div>

            <h4>
                Incoming ${callType} call
            </h4>

            <p>
                <strong id="globalIncomingCallerName"></strong>
                is calling you.
            </p>

            <p>
                <span id="globalIncomingCallCountdown">
                    30
                </span>
                seconds remaining
            </p>

            <div class="incoming-call-actions">

                <button
                    type="button"
                    id="globalRejectIncomingCall"
                    class="btn btn-danger"
                >
                    Decline
                </button>

                <button
                    type="button"
                    id="globalAcceptIncomingCall"
                    class="btn btn-success"
                >
                    Accept
                </button>

            </div>

        </div>

    `;


    document.body.appendChild(
        overlay
    );

    document.getElementById("globalIncomingCallerName").textContent = callerName;


    document
        .getElementById(
            "globalAcceptIncomingCall"
        )
        .addEventListener(
            "click",
            function () {

                answerIncomingCall(
                    call
                );

            }
        );


    document
        .getElementById(
            "globalRejectIncomingCall"
        )
        .addEventListener(
            "click",
            function () {

                rejectIncomingCall(
                    call.call_id
                );

            }
        );


    let secondsRemaining =
        30;


    const countdownElement =
        document.getElementById(
            "globalIncomingCallCountdown"
        );


    clearIncomingCallTimeout();


    incomingCallTimeout =
        setInterval(
            function () {

                secondsRemaining--;


                if (countdownElement) {

                    countdownElement.textContent =
                        secondsRemaining;

                }


                if (
                    secondsRemaining <= 0
                ) {

                    rejectIncomingCall(call.call_id, true);

                }

            },
            1000
        );

}


/* =========================================================
   CLEAR INCOMING CALL
========================================================= */

function clearGlobalIncomingCall() {

    clearIncomingCallTimeout();


    const overlay =
        document.getElementById(
            "globalIncomingCallOverlay"
        );


    if (overlay) {

        overlay.remove();

    }


    incomingCallId =
        null;

}


/* =========================================================
   ANSWER INCOMING CALL
========================================================= */

async function answerIncomingCall(call) {

    if (!call || !call.call_id) {

        return;

    }


    const callId =
        Number(call.call_id);


    /*
     * Prevent double acceptance.
     */

    if (
        currentCallId ||
        incomingCallId !== callId
    ) {

        console.warn(
            "This incoming call is already being handled."
        );

        return;

    }


    clearGlobalIncomingCall();

    currentCallType = call.call_type;

    try {

        const constraints = {

            audio: true,

            video:
                call.call_type === "VIDEO"

        };


        localStream =
            await navigator.mediaDevices.getUserMedia(
                constraints
            );


        console.log(
            "Incoming call media access granted."
        );


        const response =
            await fetch(
                `/api/messaging/calls/${callId}/accept/`,
                {

                    method: "POST",

                    headers: {

                        "Content-Type":
                            "application/json",

                        "X-CSRFToken":
                            getCookie(
                                "csrftoken"
                            )

                    },

                    credentials:
                        "same-origin"

                }
            );


        if (!response.ok) {

            const errorData =
                await response.json()
                    .catch(
                        () => ({})
                    );


            throw new Error(
                errorData.detail ||
                "Unable to accept the call."
            );

        }


        const callData =
            await response.json();


        console.log(
            "Call accepted:",
            callData
        );


        currentCallId =
            Number(callData.id);


        if (
            callData.participants
        ) {

            callData.participants.forEach(
                function (participant) {

                    const user =
                        participant.user;

                    if (
                        user &&
                        Number(user.id) !==
                        currentUserId
                    ) {

                        callParticipants[
                            Number(user.id)
                        ] = user;

                    }

                }
            );

        }


        showCallInterface(
            call.call_type,
            callData.participants || [],
            "Connecting audio and video…"
        );


        const localVideo =
            document.getElementById(
                "localVideo"
            );


        if (localVideo) {

            localVideo.srcObject =
                localStream;

        }


        await connectCallSocket(
            currentCallId
        );


        console.log(
            "Connected to incoming call."
        );


    } catch (error) {

        console.error(
            "Unable to accept incoming call:",
            error
        );


        if (currentCallId === callId) {
            await endWebRTCCall();
        } else {
            await rejectIncomingCall(callId);
            cleanupWebRTC();
        }


        alert(
            error.message ||
            "Unable to answer the call."
        );

    }

}


/* =========================================================
   REJECT INCOMING CALL
========================================================= */

async function rejectIncomingCall(
    callId,
    timedOut = false
) {

    const id =
        Number(callId);


    clearGlobalIncomingCall();


    try {

        const response =
            await fetch(
                `/api/messaging/calls/${id}/reject/`,
                {

                    method: "POST",

                    headers: {

                        "Content-Type":
                            "application/json",

                        "X-CSRFToken":
                            getCookie(
                                "csrftoken"
                            )

                    },

                    credentials:
                        "same-origin",

                    body: JSON.stringify({
                        timed_out: timedOut,
                    })

                }
            );


        if (!response.ok) {

            const errorData =
                await response.json()
                    .catch(
                        () => ({})
                    );


            console.warn(
                "Unable to reject call:",
                errorData
            );

        } else {

            console.log(
                "Incoming call rejected."
            );

        }

    } catch (error) {

        console.error(
            "Error rejecting call:",
            error
        );

    }

}


/* =========================================================
   GLOBAL USER WEBSOCKET
========================================================= */

let awinlinkUserSocket = null;
let awinlinkUserSocketReconnectTimer = null;
let awinlinkUserSocketRetryDelay = 1000;


function scheduleGlobalUserSocketReconnect() {
    if (!currentUserId || awinlinkUserSocketReconnectTimer) return;

    const delay = awinlinkUserSocketRetryDelay + Math.random() * 500;
    awinlinkUserSocketRetryDelay = Math.min(awinlinkUserSocketRetryDelay * 2, 30000);
    awinlinkUserSocketReconnectTimer = setTimeout(function () {
        awinlinkUserSocketReconnectTimer = null;
        connectGlobalUserSocket();
    }, delay);
}


function connectGlobalUserSocket() {

    if (
        !currentUserId
    ) {

        return;

    }


    if (
        awinlinkUserSocket &&
        [WebSocket.CONNECTING, WebSocket.OPEN].includes(
            awinlinkUserSocket.readyState
        )
    ) {

        return;

    }


    const protocol =
        location.protocol === "https:"
            ? "wss"
            : "ws";


    const socketUrl =
        `${protocol}://${window.location.host}/ws/user/`;


    let socket;
    try {
        socket = new WebSocket(socketUrl);
    } catch (error) {
        console.warn("Unable to create Awinlink global WebSocket:", error);
        scheduleGlobalUserSocketReconnect();
        return;
    }

    awinlinkUserSocket = socket;


    socket.onopen =
        function () {

            if (awinlinkUserSocket !== socket) return;

            awinlinkUserSocketRetryDelay = 1000;
            if (awinlinkUserSocketReconnectTimer) {
                clearTimeout(awinlinkUserSocketReconnectTimer);
                awinlinkUserSocketReconnectTimer = null;
            }

            console.log(
                "Connected to Awinlink global user WebSocket."
            );

        };


    socket.onmessage =
        function (event) {

            try {

                const data =
                    JSON.parse(
                        event.data
                    );


                console.log(
                    "GLOBAL AWINLINK EVENT:",
                    JSON.stringify(
                        data,
                        null,
                        2
                    )
                );


                if (
                    data.type ===
                    "incoming_call"
                ) {

                    console.log(
                        "Incoming Awinlink call:",
                        data
                    );


                    showIncomingCall(
                        data
                    );

                }

                if (data.type === "notification_created") {
                    window.dispatchEvent(
                        new CustomEvent("awinlink:notification", {
                            detail: data.notification,
                        })
                    );
                }

            } catch (error) {

                console.error(
                    "Global WebSocket message error:",
                    error
                );

            }

        };


    socket.onerror =
        function (error) {

            console.warn(
                "Awinlink global WebSocket error:",
                error
            );

            socket.close();

        };


    socket.onclose =
        function () {

            console.log(
                "Awinlink global WebSocket disconnected."
            );

            if (awinlinkUserSocket === socket) {
                awinlinkUserSocket = null;
                scheduleGlobalUserSocketReconnect();
            }

        };

}


/* =========================================================
   START GLOBAL USER SOCKET
========================================================= */

if (currentUserId) {

    connectGlobalUserSocket();

}


function setCallStatus(message) {
    const status = document.getElementById("awinlinkCallStatus");
    if (status) status.textContent = message;
}


function startCallTimer() {
    if (callTimerInterval) return;

    callConnectedAt = Date.now();
    const timer = document.getElementById("awinlinkCallTimer");

    const updateTimer = function () {
        if (!timer || !callConnectedAt) return;
        const elapsedSeconds = Math.floor((Date.now() - callConnectedAt) / 1000);
        const minutes = String(Math.floor(elapsedSeconds / 60)).padStart(2, "0");
        const seconds = String(elapsedSeconds % 60).padStart(2, "0");
        timer.textContent = `${minutes}:${seconds}`;
    };

    updateTimer();
    callTimerInterval = setInterval(updateTimer, 1000);
}


function stopCallTimer() {
    if (callTimerInterval) clearInterval(callTimerInterval);
    callTimerInterval = null;
    callConnectedAt = null;
}