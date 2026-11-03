/*
 * Runs Oxigraph (SPARQL in WebAssembly) off the page's thread, so loading the data doesn't
 * freeze the page. Messages in: {load: [[graph IRI, url], ...]} once, then {id, query}.
 * Messages out: {loaded, triples, ms} or {error}; then for each query {id, result} or {id, error}.
 * A result is {vars, rows} for SELECT, {boolean} for ASK, or {turtle} for CONSTRUCT and DESCRIBE.
 * Terms are sent as plain objects: {type, value, lang, datatype}.
 */
import init, * as ox from './oxigraph/web.js';

let store;

function term(t) {
    if (!t) return null;
    if (t.termType === 'Literal') {
        return { type: 'literal', value: t.value, lang: t.language || undefined,
                 datatype: t.datatype && !t.language ? t.datatype.value : undefined };
    }
    return { type: t.termType === 'NamedNode' ? 'uri' : 'bnode', value: t.value };
}

async function load(graphs) {
    const start = performance.now();
    await init();
    store = new ox.Store();
    await Promise.all(graphs.map(async ([graph, url]) => {
        const text = await (await fetch(url)).text();
        store.load(text, { format: 'text/turtle', to_graph_name: ox.namedNode(graph) });
    }));
    return { loaded: true, triples: store.size, ms: Math.round(performance.now() - start) };
}

function run(query) {
    const options = { use_default_graph_as_union: true };
    const result = store.query(query, options);
    if (typeof result === 'boolean') return { boolean: result };
    if (Array.isArray(result) && result.length && !(result[0] instanceof Map)) {
        return { turtle: store.query(query, { ...options, results_format: 'text/turtle' }) };
    }
    const vars = [];
    const rows = result.map(binding => {
        const row = {};
        for (const [k, v] of binding) {
            if (!vars.includes(k)) vars.push(k);
            row[k] = term(v);
        }
        return row;
    });
    /* the variables in the order the query names them */
    const named = [...query.matchAll(/\?(\w+)/g)].map(m => m[1]);
    vars.sort((a, b) => (named.indexOf(a) + 1 || 1e9) - (named.indexOf(b) + 1 || 1e9));
    return { vars, rows };
}

self.onmessage = async ({ data }) => {
    if (data.load) {
        try { self.postMessage(await load(data.load)); }
        catch (e) { self.postMessage({ error: String(e) }); }
        return;
    }
    const start = performance.now();
    try { self.postMessage({ id: data.id, result: run(data.query), ms: Math.round(performance.now() - start) }); }
    catch (e) { self.postMessage({ id: data.id, error: String(e) }); }
};
