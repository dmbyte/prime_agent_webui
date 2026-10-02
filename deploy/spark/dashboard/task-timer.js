"use strict";
// A nonmodal prompt keeps the conversation usable while awaiting a decision.
window.PrimeTaskTimer = (() => {
  const cards = new Map();
  let panel;
  function render(tasks, request) {
    if (!panel) {
      panel = document.createElement("aside");
      panel.id = "taskTimerPrompts";
      panel.setAttribute("aria-label", "Task time limit warnings");
      document.body.append(panel);
    }
    const near = tasks.filter(task => task.status === "running" && task.timerWarning);
    for (const [id, card] of cards) {
      if (!near.some(task => task.id === id)) { card.root.remove(); cards.delete(id); }
    }
    for (const task of near) {
      let card = cards.get(task.id);
      if (!card) {
        const root = document.createElement("section"), title = document.createElement("strong"),
          detail = document.createElement("p"), actions = document.createElement("div"),
          extend = document.createElement("button"), keep = document.createElement("button"),
          status = document.createElement("p");
        root.className = "task-timer-prompt";
        title.textContent = "This task is nearing its time limit";
        status.setAttribute("role", "status");
        extend.textContent = "Extend 30 minutes";
        keep.textContent = "Keep deadline";
        actions.append(extend, keep); root.append(title, detail, actions, status); panel.append(root);
        card = {root, title, detail, extend, keep, status, pending: false, keptRevision: null};
        cards.set(task.id, card);
        extend.onclick = async () => {
          if (card.pending) return;
          card.pending = true; extend.disabled = true; status.textContent = "Extending…";
          try {
            const result = await request("/api/tasks/extend", {method: "POST", headers: {"Content-Type": "application/json"},
              body: JSON.stringify({id: task.id, timerRevision: card.task.timerRevision})});
            Object.assign(card.task, result);
            status.textContent = `Extended by 30 minutes. New deadline: ${new Date(result.deadlineEpoch * 1000).toLocaleTimeString()}.`;
            // Suppress another click until the next normal task poll.
            card.pending = true;
          } catch (error) { status.textContent = error.message; card.pending = false; extend.disabled = false; }
        };
        keep.onclick = () => {
          card.keptRevision = card.task.timerRevision;
          status.textContent = "Deadline kept. You can still extend before it expires.";
        };
      }
      card.task = task;
      const seconds = Math.max(0, Math.ceil(task.remainingSeconds || 0));
      card.detail.textContent = `${task.topic || "Task"} — ${Math.floor(seconds / 60)}m ${seconds % 60}s remaining. Without an extension, it will stop at ${new Date(task.deadlineEpoch * 1000).toLocaleTimeString()}.`;
      card.extend.disabled = card.pending || !task.timerExtendable;
      card.keep.hidden = card.keptRevision === task.timerRevision || !task.timerExtendable;
      if (!task.timerExtendable && !card.pending) card.status.textContent = "The runtime ceiling has been reached; this task cannot be extended further.";
    }
    panel.hidden = cards.size === 0;
  }
  return {render};
})();
