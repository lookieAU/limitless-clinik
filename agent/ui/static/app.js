const $ = (selector, root = document) => root.querySelector(selector);
const messages = $("#messages");

function scrollDown() {
  if (messages) messages.scrollTop = messages.scrollHeight;
}

function bubble(role, text) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  const p = document.createElement("p");
  p.textContent = text;
  div.append(p);
  messages.append(div);
  scrollDown();
  return div;
}

function typing() {
  const div = document.createElement("div");
  div.className = "bubble agent typing";
  div.innerHTML = "<span></span><span></span><span></span>";
  messages.append(div);
  scrollDown();
  return div;
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
    bubble("customer", text);
    const dots = typing();
    const body = new FormData();
    body.append("text", text);
    body.append("client_msg_id", crypto.randomUUID());
    try {
      const response = await fetch("/ui/send", { method: "POST", body });
      dots.outerHTML = response.ok ? await response.text() : '<div class="bubble agent"><p>Something went wrong — please try again.</p></div>';
    } catch {
      dots.remove();
      bubble("agent", "Connection problem — please try again.");
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
  const status = $("#call-status");
  const segments = new Map();
  let room = null;
  let dots = null;

  const show = (id, mine, text) => {
    if (!text.trim()) return;
    if (!segments.has(id)) {
      if (!mine && dots) { dots.remove(); dots = null; }
      segments.set(id, bubble(mine ? "customer" : "agent", text));
    }
    segments.get(id).querySelector("p").textContent = text;
    scrollDown();
  };

  const ended = () => {
    document.querySelectorAll("audio[data-clinik]").forEach((el) => el.remove());
    if (dots) { dots.remove(); dots = null; }
    room = null;
    button.textContent = "Start call";
    button.classList.remove("live");
    status.textContent = "Call ended";
    refreshPanels();
  };

  button.addEventListener("click", async () => {
    if (room) { await room.disconnect(); return; }
    const { Room, RoomEvent } = window.LivekitClient;
    button.disabled = true;
    status.textContent = "Connecting…";
    try {
      const response = await fetch("/ui/voice/token");
      if (!response.ok) throw new Error("voice unavailable");
      const { url, token } = await response.json();
      room = new Room();
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind !== "audio") return;
        const element = track.attach();
        element.dataset.clinik = "1";
        document.body.append(element);
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
      button.textContent = "End call";
      button.classList.add("live");
      status.textContent = "Listening — just talk";
    } catch (error) {
      status.textContent = `Couldn't start the call (${error.message})`;
      room = null;
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
      const result = $("#result");
      result.textContent = "Working…";
      const response = await fetch(form.action, { method: "POST", body });
      result.innerHTML = await response.text();
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
