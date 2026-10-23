const $ = (selector, root = document) => root.querySelector(selector);
const messages = $("#messages");

function scrollDown() {
  if (messages) messages.scrollTop = messages.scrollHeight;
}

function row(role, text) {
  const wrapper = document.createElement("div");
  wrapper.className = `msg ${role}`;
  if (role === "agent") {
    const avatar = document.createElement("span");
    avatar.className = "avatar small";
    avatar.textContent = "C";
    wrapper.append(avatar);
  }
  const body = document.createElement("div");
  body.className = "msg-body";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  bubble.append(paragraph);
  body.append(bubble);
  wrapper.append(body);
  messages.append(wrapper);
  scrollDown();
  return wrapper;
}

function typing() {
  const wrapper = document.createElement("div");
  wrapper.className = "msg agent typing";
  wrapper.innerHTML = '<span class="avatar small">C</span><div class="msg-body"><div class="bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div></div>';
  messages.append(wrapper);
  scrollDown();
  return wrapper;
}

async function refreshPanels() {
  const panels = $("#panels");
  if (!panels) return;
  const response = await fetch("/ui/panels");
  if (response.ok) panels.innerHTML = await response.text();
}

function setupChat() {
  const composer = $("#composer");
  if (!composer) return;
  composer.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = composer.elements.text;
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    input.disabled = true;
    row("user", text);
    const dots = typing();
    const body = new FormData();
    body.append("text", text);
    body.append("client_msg_id", crypto.randomUUID());
    try {
      const response = await fetch("/ui/send", { method: "POST", body });
      if (!response.ok) throw new Error(String(response.status));
      dots.outerHTML = await response.text();
    } catch {
      dots.remove();
      row("agent", "Something went wrong. Please try again.");
    }
    input.disabled = false;
    input.focus();
    scrollDown();
    refreshPanels();
  });
}

function setupVoice() {
  const button = $("#call");
  if (!button) return;
  const title = $("#call-title");
  const status = $("#call-status");
  const segments = new Map();
  let room = null;
  let dots = null;

  const setState = (heading, detail, live) => {
    title.textContent = heading;
    status.textContent = detail;
    button.classList.toggle("live", live);
    button.innerHTML = live ? button.dataset.end : button.dataset.mic;
    button.setAttribute("aria-label", live ? "End call" : "Start call");
  };

  const show = (id, mine, text) => {
    if (!text.trim()) return;
    if (!segments.has(id)) {
      if (!mine && dots) { dots.remove(); dots = null; }
      segments.set(id, row(mine ? "user" : "agent", text));
    }
    segments.get(id).querySelector("p").textContent = text;
    scrollDown();
  };

  const ended = () => {
    document.querySelectorAll("audio[data-clinik]").forEach((element) => element.remove());
    if (dots) { dots.remove(); dots = null; }
    room = null;
    setState("Call ended", "Switch mode or start again for a new conversation", false);
    refreshPanels();
  };

  button.addEventListener("click", async () => {
    if (room) { await room.disconnect(); return; }
    const { Room, RoomEvent } = window.LivekitClient;
    button.disabled = true;
    setState("Connecting…", "Allow the microphone if your browser asks", false);
    try {
      const response = await fetch("/ui/voice/token");
      if (!response.ok) throw new Error("voice is not configured");
      const { url, token } = await response.json();
      room = new Room();
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind !== "audio") return;
        const element = track.attach();
        element.dataset.clinik = "1";
        document.body.append(element);
      });
      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        if (!room) return;
        const agentSpeaking = speakers.some((speaker) => speaker.identity !== room.localParticipant.identity);
        setState(agentSpeaking ? "Clinik is speaking" : "Listening", "Tap the red button to end the call", true);
      });
      room.on(RoomEvent.Disconnected, ended);
      room.registerTextStreamHandler("lk.transcription", async (reader, participant) => {
        const mine = participant.identity === room.localParticipant.identity;
        const id = reader.info.attributes?.["lk.segment_id"] || reader.info.id;
        let text = "";
        for await (const chunk of reader) { text += chunk; show(id, mine, text); }
        if (mine && reader.info.attributes?.["lk.transcription_final"] === "true" && !dots) dots = typing();
      });
      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true);
      setState("Listening", "Tap the red button to end the call", true);
    } catch (error) {
      room = null;
      setState("Couldn't start the call", error.message, false);
    }
    button.disabled = false;
  });
}

function setupForms() {
  document.querySelectorAll("form[data-async]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (form.dataset.confirm && !confirm(form.dataset.confirm)) return;
      const body = new FormData(form);
      if (event.submitter?.name) body.append(event.submitter.name, event.submitter.value);
      const message = $("#result span");
      message.textContent = "Working…";
      const response = await fetch(form.action, { method: "POST", body });
      message.innerHTML = await response.text();
      $("#result").scrollIntoView({ behavior: "smooth", block: "center" });
      const activity = $("#activity");
      if (activity) activity.innerHTML = await (await fetch("/admin/activity")).text();
    });
  });
}

function setupLive() {
  if (!$("#panels")) return;
  const events = new EventSource("/ui/stream");
  events.addEventListener("panels", refreshPanels);
}

setupChat();
setupVoice();
setupForms();
setupLive();
scrollDown();
