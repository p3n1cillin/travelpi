const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

let currentTarget = "";
const repeatKeys = new Set([
  "up", "down", "left", "right", "volume_up", "volume_down", "rewind", "fast_forward",
]);

async function api(path, payload = null) {
  const options = payload
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 1800);
}

function setStatus(message, ok = true) {
  const node = $("#status");
  node.textContent = message;
  node.classList.toggle("bad", !ok);
}

function optionLabel(device) {
  const state = device.state === "device" ? "connected" : device.state;
  return `${device.label} · ${state}`;
}

async function loadDevices() {
  const [health, devices] = await Promise.all([api("/api/health"), api("/api/discover")]);
  currentTarget = health.target || "";
  const select = $("#deviceSelect");
  select.innerHTML = "";
  const list = devices.length
    ? devices
    : [{ target: currentTarget, label: currentTarget || "No Fire TV found", state: "unknown" }];
  list.forEach((device) => {
    const option = document.createElement("option");
    option.value = device.target;
    option.textContent = optionLabel(device);
    option.selected = device.target === currentTarget;
    select.append(option);
  });
  if (!currentTarget && devices[0]?.target) {
    await connect(devices[0].target, false);
  } else {
    const connected = health.devices.some((device) => device.state === "device");
    setStatus(health.mock ? "Mock mode" : connected ? "Connected" : "Ready");
  }
  renderAccess(health.network?.urls || []);
  loadApps();
}

async function connect(target, notify = true) {
  if (!target) return;
  await api("/api/connect", { target });
  currentTarget = target;
  setStatus("Connected");
  if (notify) toast("Connected");
}

async function loadApps() {
  try {
    const apps = await api("/api/apps");
    const root = $("#appRow");
    root.innerHTML = "";
    apps.slice(0, 8).forEach((app) => {
      const button = document.createElement("button");
      button.textContent = app.name;
      button.dataset.package = app.package;
      button.addEventListener("click", async () => {
        try {
          await api("/api/launch", { package: app.package });
          toast(`Opened ${app.name}`);
        } catch (error) {
          toast(error.message);
        }
      });
      root.append(button);
    });
  } catch {
    // App shortcuts are optional; the remote itself should stay usable.
  }
}

function renderAccess(urls) {
  const root = $("#accessList");
  root.innerHTML = "";
  urls.forEach((item) => {
    const row = document.createElement("a");
    row.href = item.url;
    row.textContent = `${item.label}: ${item.url}`;
    root.append(row);
  });
}

function press(key, longpress = false) {
  fetch(`/k/${encodeURIComponent(key)}${longpress ? "?long=1" : ""}`, {
    cache: "no-store",
    keepalive: true,
    priority: "high",
  }).catch((error) => toast(error.message));
  if (navigator.vibrate) navigator.vibrate(8);
}

$$("[data-key]").forEach((button) => {
  let repeatTimer = null;
  let longTimer = null;
  let longSent = false;

  const clearTimers = () => {
    window.clearTimeout(repeatTimer);
    window.clearTimeout(longTimer);
    repeatTimer = null;
    longTimer = null;
  };

  button.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    button.classList.add("pressed");
    longSent = false;
    if (button.dataset.longKey) {
      longTimer = window.setTimeout(() => {
        longSent = true;
        press(button.dataset.longKey, true);
      }, 520);
    }
    press(button.dataset.key);
    if (repeatKeys.has(button.dataset.key)) {
      const repeat = () => {
        press(button.dataset.key);
        repeatTimer = window.setTimeout(repeat, 105);
      };
      repeatTimer = window.setTimeout(repeat, 280);
    }
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((eventName) => {
    button.addEventListener(eventName, () => {
      clearTimers();
      button.classList.remove("pressed");
      longSent = false;
    });
  });
});

$("#deviceSelect").addEventListener("change", async (event) => {
  try {
    await connect(event.target.value);
    await loadDevices();
  } catch (error) {
    setStatus("Error", false);
    toast(error.message);
  }
});

$("#refreshDevices").addEventListener("click", async () => {
  try {
    await loadDevices();
    toast("Devices refreshed");
  } catch (error) {
    setStatus("Offline", false);
    toast(error.message);
  }
});

$("#toggleAccess").addEventListener("click", () => {
  $("#accessList").hidden = !$("#accessList").hidden;
});

$("#sendText").addEventListener("click", async () => {
  const text = $("#text").value;
  try {
    await api("/api/text", { text });
    $("#text").value = "";
  } catch (error) {
    toast(error.message);
  }
});

$("#text").addEventListener("keydown", (event) => {
  if (event.key === "Enter") $("#sendText").click();
});

document.addEventListener("keydown", (event) => {
  const keys = {
    ArrowUp: "up",
    ArrowDown: "down",
    ArrowLeft: "left",
    ArrowRight: "right",
    Enter: "select",
    Escape: "back",
    " ": "play_pause",
  };
  if (!keys[event.key] || event.target.tagName === "INPUT") return;
  event.preventDefault();
  press(keys[event.key]);
});

loadDevices().catch((error) => {
  setStatus("Offline", false);
  toast(error.message);
});
