/*
 * The network: everyone in Who Knew Whom at once, drawn with sigma.js (WebGL) and arranged by
 * ForceAtlas2, which runs in a worker so the arranging can be watched. Everyone starts where their
 * birth year puts them, left to right, which lets the layout unfold instead of tangling. People who knew many
 * others are bigger; people with a biography are brighter. Pointing at someone shows who they
 * knew; clicking opens the bio panel (assets/js/bio-panel.js) and keeps them picked out until
 * the background is clicked. #id in the URL picks someone, as on the field page.
 * The libraries come from assets/js/vendor/sigma-bundle.min.js (tools/field-bundle).
 */
(async function () {
    const { Graph, Sigma, forceAtlas2, FA2Layout } = window.WKWField;
    const el = document.getElementById('wkw-network');
    const base = el.dataset.base;
    const layoutButton = document.getElementById('wkw-field-layout');
    const findInput = document.getElementById('wkw-field-name');
    const RUN_FOR = 30000;

    /* the WKW theme's colours (wkw-theme/scss/modules/_variables.scss); EDGE is its line colour
       (#ccc at 20%) already mixed with the background, as sigma ignores transparency in lines */
    const BIO = '#00ffcc', STUB = '#11c680', FADED = '#2fb96f', EDGE = '#3cb572';
    const EDGE_LIT = 'rgba(255, 255, 255, 0.8)';

    await document.fonts.load('20px HandsomeProRegular');
    const data = await (await fetch(el.dataset.graph)).json();

    /* a fixed starting arrangement, so the layout looks much the same each time */
    let seed = 42;
    const random = () => (seed = (seed * 16807) % 2147483647) / 2147483647;

    const graph = new Graph({ type: 'undirected' });
    for (const [id, name, bio, year] of data.nodes) {
        graph.addNode(id, { label: name, bio, x: ((year ?? 1800) - 1800) * 8, y: (random() - 0.5) * 800, color: bio ? BIO : STUB });
    }
    for (const [a, b] of data.links) graph.addEdge(data.nodes[a][0], data.nodes[b][0]);
    graph.forEachNode((n, a) => graph.setNodeAttribute(n, 'size', 1 + Math.sqrt(graph.degree(n)) * 0.9));
    document.getElementById('wkw-field-count').textContent =
        `${graph.order.toLocaleString('en-GB')} people, ${graph.size.toLocaleString('en-GB')} acquaintances.`;

    /* names for the find box, alphabetically */
    const byName = new Map();
    const options = document.getElementById('wkw-field-names');
    [...data.nodes].sort((a, b) => a[1].localeCompare(b[1])).forEach(([id, name]) => {
        byName.set(name.toLocaleLowerCase(), id);
        const o = document.createElement('option');
        o.value = name;
        options.append(o);
    });

    /* the picked-out person: hovered, else clicked */
    let hovered = null, selected = null, lit = new Set();
    function focus() {
        const f = hovered || selected;
        lit = f ? new Set([f, ...graph.neighbors(f)]) : new Set();
        renderer.refresh({ skipIndexation: true });
    }

    function drawHover(context, d, settings) {
        /* the name on the theme's darker green, rather than sigma's white box */
        const size = settings.labelSize, font = settings.labelFont;
        context.font = `${size}px ${font}`;
        const w = context.measureText(d.label).width;
        context.fillStyle = 'rgba(17, 120, 63, 0.85)';
        context.beginPath();
        context.roundRect(d.x + d.size + 2, d.y - size / 2 - 6, w + 12, size + 12, 8);
        context.fill();
        context.fillStyle = '#ffffff';
        context.fillText(d.label, d.x + d.size + 8, d.y + size / 3);
    }

    const renderer = new Sigma(graph, el, {
        labelFont: 'HandsomeProRegular, sans-serif',
        labelSize: 18,
        labelWeight: 'normal',
        labelColor: { color: BIO },
        labelDensity: 0.6,
        labelRenderedSizeThreshold: 9,
        defaultEdgeColor: EDGE,
        defaultDrawNodeHover: drawHover,
        zIndex: true,
        minCameraRatio: 0.03,
        maxCameraRatio: 2,
        nodeReducer(node, d) {
            if (!lit.size) return d;
            if (!lit.has(node)) return { ...d, color: FADED, label: '', zIndex: 0 };
            return { ...d, zIndex: 1, forceLabel: true, highlighted: node === (hovered || selected) };
        },
        edgeReducer(edge, d) {
            if (!lit.size) return d;
            const f = hovered || selected;
            return graph.hasExtremity(edge, f) ? { ...d, color: EDGE_LIT, size: 1.2, zIndex: 1 } : { ...d, hidden: true };
        },
    });

    renderer.on('enterNode', ({ node }) => { hovered = node; el.style.cursor = 'pointer'; focus(); });
    renderer.on('leaveNode', () => { hovered = null; el.style.cursor = ''; focus(); });
    renderer.on('clickNode', ({ node }) => select(node, false));
    renderer.on('clickStage', () => { if (selected) panel.hide(); });

    const panel = wkwBioPanel(base, {
        onHide() {
            selected = null;
            history.replaceState(null, '', location.pathname + location.search);
            focus();
        },
        extra: id => `<p class="wkw-field-link"><a href="${base}field/#${id}">See ${graph.getNodeAttribute(id, 'label')}&rsquo;s field</a></p>`,
    });

    function select(node, move) {
        selected = node;
        history.replaceState(null, '', '#' + node);
        focus();
        const a = graph.getNodeAttributes(node);
        panel.show(node, a.label, a.bio, graph.neighbors(node).map(k => {
            const b = graph.getNodeAttributes(k);
            return [k, b.label, b.bio];
        }));
        if (move) {
            const d = renderer.getNodeDisplayData(node);
            renderer.getCamera().animate({ x: d.x, y: d.y, ratio: 0.25 }, { duration: 800 });
        }
    }

    document.getElementById('wkw-field-find').addEventListener('submit', e => e.preventDefault());
    findInput.addEventListener('change', () => {
        const id = byName.get(findInput.value.trim().toLocaleLowerCase());
        if (id) { select(id, true); findInput.blur(); }
    });

    /* ForceAtlas2, in a worker; stops by itself after RUN_FOR */
    const settings = forceAtlas2.inferSettings(graph);
    Object.assign(settings, { barnesHutOptimize: true, gravity: 0.05, scalingRatio: 10, slowDown: 2 });
    const layout = new FA2Layout(graph, { settings });
    let timer;
    function run() {
        layout.start();
        layoutButton.textContent = 'Stop arranging';
        clearTimeout(timer);
        timer = setTimeout(stop, RUN_FOR);
    }
    function stop() {
        layout.stop();
        clearTimeout(timer);
        layoutButton.textContent = 'Arrange again';
    }
    layoutButton.disabled = false;
    layoutButton.addEventListener('click', () => (layout.isRunning() ? stop() : run()));
    run();

    const fromHash = decodeURIComponent(location.hash.slice(1));
    if (graph.hasNode(fromHash)) setTimeout(() => select(fromHash, true), RUN_FOR / 4);
})();
