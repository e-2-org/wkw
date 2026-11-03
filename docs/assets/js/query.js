/*
 * The query page: loads the three Turtle files into Oxigraph (in assets/js/query-worker.js),
 * one named graph each, and runs queries over all three. The query is kept in the URL (?query=)
 * so it can be bookmarked or shared. People link to their pages here, Wikimedia Commons
 * pictures show as thumbnails, and results can be saved as CSV.
 */
(function () {
    const form = document.getElementById('sparql-form');
    const editor = document.getElementById('sparql-query');
    const runButton = document.getElementById('sparql-run');
    const status = document.getElementById('sparql-status');
    const out = document.getElementById('sparql-results');
    const base = form.dataset.base;
    const SHOW = 1000;

    const PREFIXES = {
        foaf: 'http://xmlns.com/foaf/0.1/',
        schema: 'https://schema.org/',
        wkw: 'https://culturalcartography.net/ns#',
        skos: 'http://www.w3.org/2004/02/skos/core#',
        owl: 'http://www.w3.org/2002/07/owl#',
        rdf: 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
        rdfs: 'http://www.w3.org/2000/01/rdf-schema#',
        xsd: 'http://www.w3.org/2001/XMLSchema#',
        dcterms: 'http://purl.org/dc/terms/',
        wd: 'http://www.wikidata.org/entity/',
        wdt: 'http://www.wikidata.org/prop/direct/',
    };
    const prefixLines = Object.entries(PREFIXES).map(([p, iri]) => `PREFIX ${p}: <${iri}>`).join('\n');
    const withPrefixes = q => prefixLines + '\n\n' + q.trim() + '\n';
    const PERSON = /^https:\/\/culturalcartography\.net\/names\/([^/]+)\/#person$/;

    const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

    function compact(iri) {
        for (const [p, ns] of Object.entries(PREFIXES)) {
            if (iri.startsWith(ns) && /^[\w-]+$/.test(iri.slice(ns.length))) return p + ':' + iri.slice(ns.length);
        }
        return iri;
    }

    function cell(t) {
        if (!t) return '';
        if (t.type === 'literal') {
            const lang = t.lang ? `<span class="wkw-sparql-type">@${esc(t.lang)}</span>` : '';
            return esc(t.value) + lang;
        }
        if (t.type === 'bnode') return '_:' + esc(t.value);
        const person = t.value.match(PERSON);
        if (person) {
            return `<a href="${base}names/${person[1]}/" title="${esc(t.value)}">${esc(person[1])}</a>`;
        }
        if (/^https?:\/\/commons\.wikimedia\.org\/wiki\/Special:FilePath\/.+\.(jpe?g|png|gif|tiff?)$/i.test(t.value)) {
            const thumb = t.value.replace(/^http:/, 'https:') + '?width=120';
            return `<a href="${esc(t.value)}"><img src="${esc(thumb)}" alt="" loading="lazy" width="60"></a>`;
        }
        return `<a href="${esc(t.value)}">${esc(compact(t.value))}</a>`;
    }

    function csv(result) {
        const q = v => /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
        const lines = [result.vars.join(',')].concat(result.rows.map(r => result.vars.map(v => q(r[v] ? r[v].value : '')).join(',')));
        return URL.createObjectURL(new Blob([lines.join('\n') + '\n'], { type: 'text/csv' }));
    }

    function show(result, ms) {
        if ('error' in result) {
            out.innerHTML = `<pre class="wkw-sparql-error">${esc(result.error)}</pre>`;
            status.textContent = 'The query has a problem.';
            return;
        }
        const r = result.result;
        status.textContent = `Done in ${ms} ms.`;
        if ('boolean' in r) { out.innerHTML = `<p class="wkw-sparql-ask">${r.boolean ? 'Yes' : 'No'}</p>`; return; }
        if ('turtle' in r) { out.innerHTML = `<pre class="wkw-sparql-turtle">${esc(r.turtle)}</pre>`; return; }
        if (!r.rows.length) { out.innerHTML = '<p>No results.</p>'; return; }
        const n = r.rows.length;
        const head = `<p>${n} result${n === 1 ? '' : 's'}${n > SHOW ? `, of which the first ${SHOW} are shown` : ''}.
            <a download="wkw-results.csv" href="${csv(r)}">Download as CSV</a></p>`;
        const rows = r.rows.slice(0, SHOW).map(row => '<tr>' + r.vars.map(v => `<td>${cell(row[v])}</td>`).join('') + '</tr>').join('');
        out.innerHTML = head + `<div class="wkw-sparql-table"><table><thead><tr>${r.vars.map(v => `<th>${esc(v)}</th>`).join('')}</tr></thead>
            <tbody>${rows}</tbody></table></div>`;
    }

    const worker = new Worker(form.dataset.worker, { type: 'module' });
    let ready = false, pending = 0, nextId = 0, started = 0;
    worker.onmessage = ({ data }) => {
        if (data.loaded) {
            ready = true;
            runButton.disabled = false;
            status.textContent = `${data.triples.toLocaleString('en-GB')} triples loaded in ${(data.ms / 1000).toFixed(1)} s.`;
            if (new URLSearchParams(location.search).get('query')) run();
            return;
        }
        if (!('id' in data)) { status.textContent = 'The data could not be loaded: ' + data.error; return; }
        if (data.id !== pending) return;
        runButton.disabled = false;
        show(data, data.ms ?? Math.round(performance.now() - started));
    };
    const words = form.dataset.graphs.split(/\s+/);
    const graphs = [];
    for (let i = 0; i < words.length; i += 2) graphs.push([words[i], new URL(words[i + 1], location.href).href]);
    worker.postMessage({ load: graphs });

    function run() {
        if (!ready) return;
        pending = ++nextId;
        started = performance.now();
        runButton.disabled = true;
        status.textContent = 'Running…';
        const url = new URL(location.href);
        url.searchParams.set('query', editor.value);
        history.replaceState(null, '', url);
        worker.postMessage({ id: pending, query: editor.value });
    }

    form.addEventListener('submit', e => { e.preventDefault(); run(); });
    editor.addEventListener('keydown', e => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); }
    });
    document.querySelectorAll('.wkw-sparql-example').forEach(b => b.addEventListener('click', () => {
        editor.value = withPrefixes(b.dataset.query);
        run();
        editor.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }));

    const fromUrl = new URLSearchParams(location.search).get('query');
    editor.value = fromUrl || withPrefixes(document.querySelector('.wkw-sparql-example').dataset.query);
})();
