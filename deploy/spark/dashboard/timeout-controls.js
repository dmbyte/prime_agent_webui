"use strict";
// Minutes are the persisted/API unit. Editing a chat changes future tasks only.
window.PrimeTimeout = (() => {
  const presets = [[30,"30 minutes"],[60,"1 hour"],[120,"2 hours"],[240,"4 hours"],
    [480,"8 hours"],[1440,"1 day"],[4320,"3 days"],[10080,"1 week"],
    [20160,"2 weeks"],[40320,"4 weeks"],[80640,"8 weeks"],[129600,"90 days"]];
  function create(id, parent) {
    const label = document.createElement("label"), select = document.createElement("select");
    label.append("Task timeout"); select.id = id; select.setAttribute("aria-label", id === "taskTimeout" ? "Chat task timeout" : "Project task timeout");
    select.title = "Saved for each new task in this chat. Does not change a running task's deadline or survive a server restart. Tasks can finish earlier.";
    for (const [value, name] of presets) select.add(new Option(name, String(value)));
    label.append(select); parent.append(label);
  }
  create("taskTimeout", document.querySelector(".conversation-toolbar .task-policy-row"));
  create("projectTimeout", document.querySelector(".project-policy-grid"));
  const note = document.createElement("small");
  note.className = "muted"; note.textContent = "Task timeout applies to new tasks; changing it does not extend a running task. Server restarts still interrupt work.";
  document.querySelector(".conversation-toolbar").append(note);
  function read(id) { return Number(document.getElementById(id).value || 30); }
  function set(id, minutes) {
    const select = document.getElementById(id), value = Number(minutes ?? 30);
    for (const option of [...select.options]) if (option.dataset.custom) option.remove();
    if (!presets.some(([n]) => n === value) && Number.isInteger(value) && value > 0) {
      const option = new Option(`${value.toLocaleString()} minutes`, String(value)); option.dataset.custom = "true"; select.add(option);
    }
    select.value = String(value);
  }
  function configure(id, capabilities) {
    const select = document.getElementById(id), max = capabilities?.maximums?.runtime_minutes ?? 30;
    for (const option of select.options) option.disabled = option.hidden = Number(option.value) > max;
    if (!select.value || Number(select.value) > max) select.value = "30";
  }
  return {read, set, configure};
})();
