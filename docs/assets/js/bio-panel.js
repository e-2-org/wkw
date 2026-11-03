/*
 * The bio panel the WKW theme designed for its graph (.wkwpanel in wkw.css), shared by the field
 * and the whole-network view. show(id, name) fills it from the person's own page; people without
 * a page (the stubs) get a note instead, and the people they knew, from the graph.
 *
 *   const panel = wkwBioPanel(base, { onShow, onHide, extra(id, name) });
 *   panel.show(id, name, hasPage, knew);   // knew: [[id, name, hasPage], ...] for the stubs
 *   panel.hide();
 */
window.wkwBioPanel = function (base, options = {}) {
    const panel = document.querySelector('.wkwpanel');
    const content = panel.querySelector('.wkwpanel-content');
    const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
    const nameUrl = id => `${base}names/${id}/`;
    let current = null;

    function open(id, h1, nodes) {
        const bio = document.createElement('div');
        bio.className = 'wkwpanel-content-bio';
        bio.append(...nodes);
        if (options.extra) bio.insertAdjacentHTML('beforeend', options.extra(id));
        content.replaceChildren(h1, bio);
        panel.style.display = 'block';
        if (options.onShow) options.onShow(id);
    }

    function show(id, name, hasPage = true, knew = []) {
        current = id;
        const h1 = document.createElement('h1');
        if (!hasPage) {
            h1.textContent = name;
            const list = knew.map(([k, n, page]) => page ? `<li><a href="${nameUrl(k)}">${esc(n)}</a></li>` : `<li>${esc(n)}</li>`).join('');
            const div = document.createElement('div');
            div.innerHTML = `<p>Who Knew Whom doesn&rsquo;t have a biography of ${esc(name)} yet.</p>`
                + (list ? `<div class="linked-names"><h2 class="entry-title">${esc(name)} knew&hellip;</h2><ul class="inline-list">${list}</ul></div>` : '');
            open(id, h1, [div]);
            return;
        }
        fetch(nameUrl(id)).then(r => r.text()).then(page => {
            if (current !== id) return;
            const doc = new DOMParser().parseFromString(page, 'text/html');
            const a = document.createElement('a');
            a.href = nameUrl(id);
            a.textContent = doc.querySelector('.entry-title')?.textContent || name;
            h1.append(a);
            const nodes = [];
            const meta = doc.querySelector('.wkwname-meta');
            if (meta) nodes.push(meta);
            nodes.push(...doc.querySelector('.entry-content').childNodes);
            const knewList = doc.querySelector('.linked-names');
            if (knewList) {
                knewList.querySelector('.wkw-field-link')?.remove();
                nodes.push(knewList);
            }
            open(id, h1, nodes);
        });
    }

    function hide() {
        current = null;
        panel.style.display = 'none';
        if (options.onHide) options.onHide();
    }

    panel.querySelector('.wkwpanel-close').addEventListener('click', hide);
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && current) hide(); });
    return { show, hide };
};
