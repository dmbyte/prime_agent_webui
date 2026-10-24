/* Credentials never enter app state, localStorage, conversation settings or logs. */
(() => {
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  async function request(body, path = '/auth/credentials') {
    const headers = {};
    if (body) {
      headers['Content-Type'] = 'application/json';
      headers['X-Prime-CSRF'] = decodeURIComponent(document.cookie.split('; ').find(x => x.startsWith('prime_csrf='))?.split('=').slice(1).join('=') || '');
    }
    const response = await fetch(path, {
      method: body ? 'POST' : 'GET', headers, credentials: 'same-origin', cache: 'no-store',
      ...(body ? {body: JSON.stringify(body)} : {})
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Credential request failed');
    return data;
  }
  function section() {
    let group = document.getElementById('credentialSettings');
    if (group) return group.querySelector('.credential-list');
    const account = document.querySelector('[data-collapse-key="settings-account"]');
    if (!account) return null;
    group = el('details', '', 'collapsible-group');
    group.id = 'credentialSettings';
    const summary = el('summary', 'My credentials');
    const body = el('div', '', 'collapsible-body');
    body.append(el('p', 'Private to your login. Enabled, reviewed skills declare the fields shown here. Saved values cannot be displayed; blank fields preserve existing values.', 'muted'));
    body.append(el('p', 'Saving does not grant tool access. Bind reviewed requirements in My connections below. Private browser/KVM and IPMI/SOL require separate administrator activation and validation.', 'muted'));
    const refresh = el('button', 'Refresh requirements'); refresh.type = 'button';
    refresh.onclick = load;
    const list = el('div', '', 'credential-list'); list.setAttribute('aria-live', 'polite');
    body.append(refresh, list); group.append(summary, body);
    account.before(group);
    return list;
  }
  function card(row) {
    const box = el('div', '', 'settings-card credential-card');
    box.append(el('strong', `${row.skillName} · ${row.label}`));
    box.append(el('p', row.description || '', 'muted'));
    const status = el('p', row.status === 'saved' ? (row.adapter ? 'Saved · configure access in My connections' : 'Saved · tool integration pending') : row.status === 'inactive' ? 'Inactive requirement · delete stored values if no longer needed' : 'Required values missing');
    status.setAttribute('role', 'status'); box.append(status);
    const fields = new Map();
    for (const field of row.fields) {
      const label = el('label', `${field.label}${field.required ? ' *' : ' (optional)'}`);
      const input = document.createElement('input'); input.type = 'password';
      input.autocomplete = 'new-password'; input.maxLength = 8192;
      input.placeholder = field.configured ? 'Saved — leave blank to keep' : 'Not set';
      input.setAttribute('aria-label', field.label);
      fields.set(field.id, input); label.append(input); box.append(label);
    }
    const certificate = document.createElement('input'); certificate.type = 'checkbox';
    certificate.checked = row.ignoreCertificateErrors === true;
    certificate.setAttribute('aria-label', 'Ignore certificate errors');
    const certificateLabel = el('label', 'Ignore certificate errors'); certificateLabel.prepend(certificate);
    certificateLabel.hidden = row.status === 'inactive'; box.append(certificateLabel);
    if (row.status !== 'inactive') box.append(el('p', 'Off by default. Applies only to this saved credential when used by a supported connection adapter. Bypasses expiry, hostname and trust checks, so an impersonating server could receive your password. Does not change TLS globally or grant access. Prime’s native OpenShell HTTP adapter does not support this exception; IPMI/SOL does not use TLS. Saving changes requires renewing existing connections.', 'muted'));
    const actions = el('div', '', 'dialog-actions');
    const save = el('button', 'Save credentials'); save.type = 'button';
    save.hidden = row.status === 'inactive';
    const remove = el('button', 'Delete saved values', 'danger'); remove.type = 'button';
    remove.hidden = row.status === 'missing' && !row.fields.some(f => f.configured);
    const run = async action => {
      save.disabled = remove.disabled = true;
      const values = Object.fromEntries([...fields].map(([key, input]) => [key, input.value]));
      // Remove typed secrets from the DOM on submission, including failed requests.
      for (const input of fields.values()) input.value = '';
      try {
        await request({action, key: row.key, ...(action === 'save' ? {values, ignoreCertificateErrors: certificate.checked} : {})});
        await load();
      } catch (error) {status.textContent = error.message;}
      finally {for (const key of Object.keys(values)) values[key] = ''; save.disabled = remove.disabled = false;}
    };
    save.onclick = () => run('save');
    remove.onclick = () => {if (confirm('Delete your saved values for this connection? This does not revoke the credential at its provider.')) run('delete');};
    actions.append(save, remove); box.append(actions);
    return box;
  }
  async function load() {
    const list = section(); if (!list) return;
    list.replaceChildren(el('p', 'Loading credential requirements…', 'muted'));
    try {
      const data = await request(); list.replaceChildren();
      for (const row of data.credentials) list.append(card(row));
      if (!data.credentials.length) list.append(el('p', 'No enabled skills currently declare credential requirements.', 'muted'));
    } catch (error) {list.replaceChildren(el('p', error.message, 'muted'));}
    await loadConnections();
  }
  function connectionForm(data, current = {}) {
    const form = el('form', '', 'settings-card');
    const input = (title, type, value) => {
      const label = el('label', title), field = document.createElement('input');
      field.type = type; field.value = value; field.setAttribute('aria-label', title); label.append(field); form.append(label); return field;
    };
    const name = input('Connection name', 'text', current.name || ''); name.required = true; name.maxLength = 80;
    const select = (title, rows, value) => {
      const label = el('label', title), field = document.createElement('select');
      field.setAttribute('aria-label', title);
      for (const [id, text] of rows) {const option = el('option', text); option.value = id; field.append(option);}
      field.value = value || rows[0]?.[0] || ''; label.append(field); form.append(label); return field;
    };
    const req = select('Reviewed credential requirement', data.requirements.filter(r => r.saved).map(r => [r.key, `${r.skillName} · ${r.label}`]), current.credentialKey);
    const project = select('Allow use in', [['', 'All my chats (explicit user-wide grant)'], ...data.projects.map(p => [p.id, p.name])], current.projectId);
    const target = input('Approved BMC HTTPS IPv4 origin', 'text', current.adapter && current.adapter !== 'github-readonly' ? current.endpoint : '');
    target.placeholder = 'https://192.168.1.20';
    const expiry = input('Grant expires (1–90 days from now; saving renews)', 'number', '30'); expiry.min = '1'; expiry.max = '90'; expiry.required = true;
    const enabled = input('Enable this connection', 'checkbox', ''); enabled.checked = current.enabled !== false;
    const refreshFields = () => {
      const requirement = data.requirements.find(r => r.key === req.value);
      target.parentElement.hidden = !requirement || requirement.adapter === 'github-readonly';
      target.required = !!requirement && requirement.adapter !== 'github-readonly';
      project.disabled = !!requirement?.projectId;
      if (requirement?.projectId) project.value = requirement.projectId;
    };
    req.onchange = refreshFields; refreshFields();
    form.append(el('p', 'Saving invalidates existing task grants; new tasks receive the new grant. Credential access does not authorize publishing, rebooting or trading. SOL opening and console input require separate exact-action approval below.', 'muted'));
    const status = el('p', '', 'muted'); status.setAttribute('role', 'status');
    const save = el('button', current.id ? 'Save connection changes' : 'Add connection'); save.type = 'submit'; save.disabled = !req.options.length;
    form.append(save, status);
    form.onsubmit = async event => {
      event.preventDefault(); save.disabled = true;
      try {
        await request({action: 'save', ...(current.id ? {id: current.id} : {}), name: name.value, credentialKey: req.value,
          projectId: project.value || null, endpoint: target.value, enabled: enabled.checked,
          expiresAt: Math.floor(Date.now()/1000) + Number(expiry.value)*86400}, '/auth/connections');
        await loadConnections();
      } catch (error) {status.textContent = error.message; save.disabled = false;}
    };
    return form;
  }
  async function loadConnections() {
    let group = document.getElementById('connectionSettings');
    if (!group) {
      const previous = document.getElementById('credentialSettings'); if (!previous) return;
      group = el('details', '', 'collapsible-group'); group.id = 'connectionSettings';
      group.append(el('summary', 'My connections'), el('div', '', 'collapsible-body')); previous.after(group);
    }
    const body = group.querySelector('.collapsible-body');
    try {
      const data = await request(null, '/auth/connections'); body.replaceChildren();
      body.append(el('p', data.runtimeEnabled ? `Read-only runtime enabled. Private console runtime ${data.consoleRuntimeEnabled ? 'enabled' : 'staged/disabled'}. Connections are scoped to your account and project. Saved does not mean tested.` : 'Staged setup: runtime access is disabled. Saving here does not activate services or interrupt tasks.', 'muted'));
      const refresh = el('button', 'Refresh connections'); refresh.type = 'button'; refresh.onclick = loadConnections; body.append(refresh);
      const approvals = el('div'); approvals.id = 'connectionApprovals'; body.append(approvals);
      renderApprovals(data.consoleApprovals || []);
      for (const row of data.connections) {
        const box = el('details', '', 'settings-card'); box.append(el('summary', row.name));
        box.append(el('p', `${row.status} · ${row.enabled ? 'enabled' : 'disabled'} · expires ${new Date(row.expiresAt*1000).toLocaleString()} · ${row.operations.join(', ')}`, 'muted'));
        box.append(connectionForm(data, row));
        const remove = el('button', 'Delete connection', 'danger'); remove.type = 'button';
        remove.onclick = async () => {
          if (!confirm('Revoke this connection for tasks? Saved credentials will remain.')) return;
          remove.disabled = true;
          try {await request({action: 'delete', id: row.id}, '/auth/connections'); await loadConnections();}
          catch (error) {box.append(el('p', error.message)); remove.disabled = false;}
        };
        box.append(remove); body.append(box);
      }
      if (!data.requirements.some(r => r.saved)) body.append(el('p', 'Save credentials for a reviewed connection requirement first.', 'muted'));
      body.append(connectionForm(data));
    } catch (error) {body.replaceChildren(el('p', error.message, 'muted'));}
  }
  function renderApprovals(rows) {
    const root = document.getElementById('connectionApprovals'); if (!root) return;
    root.replaceChildren(el('strong', 'Console action approvals'));
    if (!rows.length) root.append(el('p', 'No pending actions. Refresh to check for requests.', 'muted'));
    for (const row of rows) {
      const card = el('div', '', 'settings-card');
      card.append(el('p', `${row.operation} · ${row.name || row.connection} · ${row.endpoint || 'unavailable target'}`));
      card.append(el('p', `Task ${row.taskId} · expires ${new Date(row.expiresAt*1000).toLocaleTimeString()}`, 'muted'));
      card.append(el('pre', JSON.stringify(row.arguments, null, 2)));
      card.append(el('p', 'Only approve if you understand the effect on this server. Keys/text can change BIOS, boot, or the running OS. Never enter passwords through agent console input.', 'muted'));
      for (const [label, approve] of [['Allow once', true], ['Deny', false]]) {
        const button = el('button', label); button.type = 'button';
        button.onclick = async () => {
          button.disabled = true;
          try {await request({action: 'decide-console', id: row.id, approve}, '/auth/connections'); await loadConnections();}
          catch (error) {card.append(el('p', error.message)); button.disabled = false;}
        };
        card.append(button);
      }
      root.append(card);
    }
  }
  document.querySelector('[data-panel="settings"]')?.addEventListener('click', load);
})();
