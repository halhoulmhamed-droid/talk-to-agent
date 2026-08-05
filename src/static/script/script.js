let peerConnection;
let audioContext;
let dataChannel;
let isStarting = false;
let isMuted = false;
let analyser_input, dataArray_input;
let analyser, dataArray;
let source_input = null;
let source_output = null;

const startButton = document.getElementById('start-button');
const voiceSelect = document.getElementById('voice');
const audioOutput = document.getElementById('audio-output');
const boxContainer = document.querySelector('.box-container');
const numBars = 32;
for (let i = 0; i < numBars; i++) {
    const box = document.createElement('div');
    box.className = 'box';
    boxContainer.appendChild(box);
}
// SVG Icons
const micIconSVG = `
            <svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                <line x1="12" y1="19" x2="12" y2="23"></line>
                <line x1="8" y1="23" x2="16" y2="23"></line>
            </svg>`;
const micMutedIconSVG = `
            <svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                <line x1="12" y1="19" x2="12" y2="23"></line>
                <line x1="8" y1="23" x2="16" y2="23"></line>
                <line x1="1" y1="1" x2="23" y2="23"></line>
            </svg>`;
function updateButtonState() {
    startButton.innerHTML = '';
    startButton.onclick = null;
    if (isStarting || (peerConnection && (peerConnection.connectionState === 'connecting' || peerConnection.connectionState === 'new'))) {
        startButton.innerHTML = `
                    <div class="icon-with-spinner">
                        <div class="spinner"></div>
                        <span>Connecting...</span>
                    </div>
                `;
        startButton.disabled = true;
    } else if (peerConnection && peerConnection.connectionState === 'connected') {
        const pulseContainer = document.createElement('div');
        pulseContainer.className = 'pulse-container';
        pulseContainer.innerHTML = `
                    <div class="pulse-circle"></div>
                    <span>Stop Recording</span>
                `;
        const muteToggle = document.createElement('div');
        muteToggle.className = 'mute-toggle';
        muteToggle.title = isMuted ? 'Unmute' : 'Mute';
        muteToggle.innerHTML = isMuted ? micMutedIconSVG : micIconSVG;
        muteToggle.addEventListener('click', toggleMute);
        startButton.appendChild(pulseContainer);
        startButton.appendChild(muteToggle);
        startButton.disabled = false;
    } else {
        startButton.innerHTML = 'Start Recording';
        startButton.disabled = false;
    }
}
function showError(message) {
    const toast = document.getElementById('error-toast');
    toast.textContent = message;
    toast.className = 'toast error';
    toast.style.display = 'block';
    // Hide toast after 5 seconds
    setTimeout(() => {
        toast.style.display = 'none';
    }, 5000);
}
function toggleMute(event) {
    event.stopPropagation();
    event.preventDefault();
    if (!peerConnection || peerConnection.connectionState !== 'connected') return;
    isMuted = !isMuted;
    console.log("Mute toggled:", isMuted);
    peerConnection.getSenders().forEach(sender => {
        if (sender.track && sender.track.kind === 'audio') {
            sender.track.enabled = !isMuted;
            console.log(`Audio track ${sender.track.id} enabled: ${!isMuted}`);
        }
    });
    updateButtonState();
}

function createWebRTCId() {
    if (globalThis.crypto?.randomUUID) {
        return globalThis.crypto.randomUUID();
    }

    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function fetchRTCConfiguration() {
    const response = await fetch('/config/rtc', {
        headers: { 'Accept': 'application/json' },
        cache: 'no-store',
    });
    if (!response.ok) {
        throw new Error(`RTC configuration request failed (${response.status}).`);
    }
    const configuration = await response.json();
    if (!configuration || !Array.isArray(configuration.iceServers)) {
        throw new Error('The server returned an invalid RTC configuration.');
    }
    return configuration;
}

async function setupWebRTC() {
    if (isStarting) return;
    isStarting = true;
    updateButtonState();
    let timeoutId;
    let currentPeerConnection;

    try {
        const config = await fetchRTCConfiguration();
        currentPeerConnection = new RTCPeerConnection(config);
        peerConnection = currentPeerConnection;
        const sessionId = createWebRTCId();

        timeoutId = setTimeout(() => {
            const toast = document.getElementById('error-toast');
            toast.textContent = 'Connection is taking longer than expected.';
            toast.className = 'toast warning';
            toast.style.display = 'block';
        }, 5000);

        const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaStream.getTracks().forEach(track => currentPeerConnection.addTrack(track, mediaStream));
        if (!audioContext || audioContext.state === 'closed') {
            audioContext = new AudioContext();
        }
        if (source_input) {
            try { source_input.disconnect(); } catch (e) { console.warn("Error disconnecting previous input source:", e); }
            source_input = null;
        }
        source_input = audioContext.createMediaStreamSource(mediaStream);
        analyser_input = audioContext.createAnalyser();
        console.log("analyser_input", analyser_input)
        source_input.connect(analyser_input);
        analyser_input.fftSize = 64;
        dataArray_input = new Uint8Array(analyser_input.frequencyBinCount);
        console.log("dataArray_input", dataArray_input)
        updateAudioLevel();
        currentPeerConnection.addEventListener('connectionstatechange', () => {
            const state = currentPeerConnection.connectionState;
            console.log('connectionstatechange', state);
            if (state === 'connected') {
                clearTimeout(timeoutId);
                isStarting = false;
                const toast = document.getElementById('error-toast');
                toast.style.display = 'none';
                if (analyser_input) updateAudioLevel();
                if (analyser) updateVisualization();
            } else if (['disconnected', 'failed', 'closed'].includes(state) && peerConnection === currentPeerConnection) {
                clearTimeout(timeoutId);
                isStarting = false;
                if (state !== 'closed') {
                    showError('The WebRTC connection was interrupted.');
                }
                stopWebRTC(currentPeerConnection);
            }
            updateButtonState();
        });
        currentPeerConnection.onicecandidate = async ({ candidate }) => {
            if (candidate) {
                console.debug("Sending ICE candidate", candidate);
                try {
                    const response = await fetch('/webrtc/offer', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            candidate: candidate.toJSON(),
                            webrtc_id: sessionId,
                            type: 'ice-candidate',
                        })
                    });
                    if (!response.ok) {
                        throw new Error(`ICE candidate request failed (${response.status}).`);
                    }
                    const result = await response.json();
                    if (result.status === 'failed') {
                        console.warn('ICE candidate rejected:', result.meta?.error);
                    }
                } catch (error) {
                    console.error('Failed to send ICE candidate:', error);
                }
            }
        };
        currentPeerConnection.addEventListener('track', (evt) => {
            if (evt.track.kind === 'audio' && audioOutput) {
                if (audioOutput.srcObject !== evt.streams[0]) {
                    audioOutput.srcObject = evt.streams[0];
                    console.log("audioOutput", evt.streams[0])
                    audioOutput.play().catch(e => console.error("Audio play failed:", e));
                    if (!audioContext || audioContext.state === 'closed') {
                        console.warn("AudioContext not ready for output track analysis.");
                        return;
                    }
                    if (source_output) {
                        try { source_output.disconnect(); } catch (e) { console.warn("Error disconnecting previous output source:", e); }
                        source_output = null;
                    }
                    source_output = audioContext.createMediaStreamSource(evt.streams[0]);
                    analyser = audioContext.createAnalyser();
                    source_output.connect(analyser);
                    analyser.fftSize = 2048;
                    dataArray = new Uint8Array(analyser.frequencyBinCount);
                    updateVisualization();
                }
            }
        });
        dataChannel = currentPeerConnection.createDataChannel('text');
        dataChannel.onmessage = async (event) => {
            let eventJson;
            try {
                eventJson = JSON.parse(event.data);
            } catch (error) {
                console.error('Invalid data-channel message:', error);
                return;
            }
            if (eventJson.type === "error") {
                showError(eventJson.message);
            } else if (eventJson.type === "send_input") {
                try {
                    const response = await fetch('/input_hook', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            webrtc_id: sessionId,
                            voice_name: voiceSelect.value
                        })
                    });
                    if (!response.ok) {
                        throw new Error(`Voice selection failed (${response.status}).`);
                    }
                } catch (error) {
                    console.error('Failed to initialize the voice session:', error);
                    showError('The voice session could not be initialized.');
                    stopWebRTC(currentPeerConnection);
                }
            }
        };
        const offer = await currentPeerConnection.createOffer();
        await currentPeerConnection.setLocalDescription(offer);
        const response = await fetch('/webrtc/offer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sdp: currentPeerConnection.localDescription.sdp,
                type: currentPeerConnection.localDescription.type,
                webrtc_id: sessionId,
            })
        });
        if (!response.ok) {
            throw new Error(`WebRTC offer failed (${response.status}).`);
        }
        const serverResponse = await response.json();
        if (serverResponse.status === 'failed') {
            const errorCode = serverResponse.meta?.error || 'unknown_error';
            showError(errorCode === 'concurrency_limit_reached'
                ? `Too many connections. Maximum limit is ${serverResponse.meta.limit}`
                : errorCode);
            stopWebRTC(currentPeerConnection);
            startButton.textContent = 'Start Recording';
            return;
        }
        await currentPeerConnection.setRemoteDescription(serverResponse);
        isStarting = false;
        updateButtonState();
    } catch (err) {
        clearTimeout(timeoutId);
        isStarting = false;
        console.error('Error setting up WebRTC:', err);
        const message = err?.name === 'NotAllowedError'
            ? 'Microphone permission was denied. Allow microphone access and try again.'
            : 'Failed to establish connection. Please try again.';
        showError(message);
        stopWebRTC(currentPeerConnection);
        startButton.textContent = 'Start Recording';
    }
}
function updateVisualization() {
    if (!analyser || !peerConnection || !['connected', 'connecting'].includes(peerConnection.connectionState)) {
        const bars = document.querySelectorAll('.box');
        bars.forEach(bar => bar.style.transform = 'scaleY(0.1)');
        return;
    }
    analyser.getByteFrequencyData(dataArray);
    const bars = document.querySelectorAll('.box');
    for (let i = 0; i < bars.length; i++) {
        const barHeight = (dataArray[i] / 255) * 2;
        bars[i].style.transform = `scaleY(${Math.max(0.1, barHeight)})`;
    }
    requestAnimationFrame(updateVisualization);
}
function updateAudioLevel() {
    if (!analyser_input || !peerConnection || !['connected', 'connecting'].includes(peerConnection.connectionState)) {
        const pulseCircle = document.querySelector('.pulse-circle');
        if (pulseCircle) {
            pulseCircle.style.setProperty('--audio-level', 1);
        }
        return;
    }
    analyser_input.getByteFrequencyData(dataArray_input);
    const average = Array.from(dataArray_input).reduce((a, b) => a + b, 0) / dataArray_input.length;
    const audioLevel = average / 255;
    const pulseCircle = document.querySelector('.pulse-circle');
    if (pulseCircle) {
        pulseCircle.style.setProperty('--audio-level', 1 + audioLevel);
    }
    requestAnimationFrame(updateAudioLevel);
}
function stopWebRTC(expectedPeerConnection = null) {
    if (expectedPeerConnection && peerConnection !== expectedPeerConnection) {
        return;
    }
    console.log("Running stopWebRTC");
    if (peerConnection) {
        peerConnection.getSenders().forEach(sender => {
            if (sender.track) {
                sender.track.stop();
            }
        });
        peerConnection.onicecandidate = null;
        peerConnection.ontrack = null;
        peerConnection.onicegatheringstatechange = null;
        peerConnection.onconnectionstatechange = null;
        if (dataChannel) {
            dataChannel.onmessage = null;
            try { dataChannel.close(); } catch (e) { console.warn("Error closing data channel:", e); }
            dataChannel = null;
        }
        try { peerConnection.close(); } catch (e) { console.warn("Error closing peer connection:", e); }
        peerConnection = null;
    }
    if (audioOutput) {
        audioOutput.pause();
        audioOutput.srcObject = null;
    }
    if (source_input) {
        try { source_input.disconnect(); } catch (e) { console.warn("Error disconnecting input source:", e); }
        source_input = null;
    }
    if (source_output) {
        try { source_output.disconnect(); } catch (e) { console.warn("Error disconnecting output source:", e); }
        source_output = null;
    }
    const contextToClose = audioContext;
    audioContext = null;
    if (contextToClose && contextToClose.state !== 'closed') {
        contextToClose.close().then(() => {
            console.log("AudioContext closed successfully.");
        }).catch(e => {
            console.error("Error closing AudioContext:", e);
        });
    }
    analyser_input = null;
    dataArray_input = null;
    analyser = null;
    dataArray = null;
    isMuted = false;
    isStarting = false;
    updateButtonState();
    const bars = document.querySelectorAll('.box');
    bars.forEach(bar => bar.style.transform = 'scaleY(0.1)');
    const pulseCircle = document.querySelector('.pulse-circle');
    if (pulseCircle) {
        pulseCircle.style.setProperty('--audio-level', 1);
    }
}
startButton.addEventListener('click', (event) => {
    if (event.target.closest('.mute-toggle')) {
        return;
    }
    if (peerConnection && peerConnection.connectionState === 'connected') {
        console.log("Stop button clicked");
        stopWebRTC();
    } else if (!peerConnection || ['new', 'closed', 'failed', 'disconnected'].includes(peerConnection.connectionState)) {
        console.log("Start button clicked");
        setupWebRTC();
    }
});
updateButtonState();
