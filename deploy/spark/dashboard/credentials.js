/* Credentials never enter app state, localStorage, conversation settings or logs. */
(() => {
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  async function request(body) {
    const headers = {};
    if (body) {
      headers['Content-Type'] = 'application/json';
      headers['X-Prime-CSRF'] = decodeURIComponent(document.cookie.split('; ').find(x => x.startsWith('prime_csrf='))?.split('=').slice(1).join('=') || '');
    }
    const response = await fetch('/auth/credentials', {
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
    body.append(el('p', 'Storage and setup only: runtime tool adapters are not connected yet. Saving here does not give an agent access to these secrets.', 'muted'));
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
    const status = el('p', row.status === 'saved' ? 'Saved · tool integration pending' : row.status === 'inactive' ? 'Inactive requirement · delete stored values if no longer needed' : 'Required values missing');
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
        await request({action, key: row.key, ...(action === 'save' ? {values} : {})});
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
  }
  document.querySelector('[data-panel="settings"]')?.addEventListener('click', load);
})();
