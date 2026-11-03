/*
 * The field: the force-directed graph from the WKW theme (wkw-theme/js/wkw.js), finished and ported to d3 v7.
 *
 * Around one person: them (level 1, the large name), everyone they knew (level 2) and everyone
 * those people knew (level 3, circles only), as the theme's /d3/{id} API built it. Circles can
 * be dragged; double-clicking one centres the graph on that person. Clicking the name of anyone
 * with a page opens their bio in the panel, and the graph moves left to make room.
 *
 * The person is the one in the URL's #hash (e.g. field/#charles-babbage), else data-start.
 * The network is assets/data/graph.json: nodes are [id, name, has a page], links index pairs.
 */
(function () {
    const svg = d3.select('#wkw-field');
    const el = svg.node();
    const base = el.dataset.base;
    const breakpoint = 1024;
    let width, height, simulation, nodes = [], neighbours, byId;

    const bg = svg.append('rect').attr('class', 'bg');
    const zoomLayer = svg.append('g');
    const gl = zoomLayer.append('g').attr('class', 'links');
    const gn = zoomLayer.append('g').attr('class', 'nodes');
    const gt = zoomLayer.append('g').attr('class', 'labels');
    svg.call(d3.zoom().scaleExtent([0.2, 4]).filter(e => e.type === 'wheel' || e.target === bg.node() || e.touches)
        .on('zoom', e => zoomLayer.attr('transform', e.transform)))
        .on('dblclick.zoom', null);

    function size() {
        width = window.innerWidth;
        height = window.innerHeight;
        svg.attr('width', width).attr('height', height);
        bg.attr('width', width).attr('height', height);
    }

    /* the theme's get_d3_data: the person, who they knew, and who those people knew */
    function network(id) {
        const level = new Map([[id, 1]]);
        const links = [];
        const seen = new Set();
        const link = (a, b) => {
            const key = a < b ? a + ' ' + b : b + ' ' + a;
            if (!seen.has(key)) { seen.add(key); links.push({ source: a, target: b }); }
        };
        for (const k of neighbours.get(id)) { if (!level.has(k)) level.set(k, 2); link(id, k); }
        for (const k of neighbours.get(id)) {
            for (const j of neighbours.get(k)) { if (!level.has(j)) level.set(j, 3); link(k, j); }
        }
        const old = new Map(nodes.map(n => [n.id, n]));
        const list = [...level].map(([n, l]) => {
            const node = old.get(n) || { x: width / 2 + (Math.random() - 0.5) * 50, y: height / 2 + (Math.random() - 0.5) * 50 };
            return Object.assign(node, { id: n, name: byId.get(n)[1], bio: byId.get(n)[2], level: l });
        });
        return { nodes: list, links };
    }

    const cls = (prefix, d) => `${prefix} level${d.level}${d.bio ? ' bio' : ''}`;

    function show(id) {
        if (!byId.has(id)) id = el.dataset.start;
        const graph = network(id);
        nodes = graph.nodes;
        document.title = `${byId.get(id)[1]}’s field – Who Knew Whom`;

        const link = gl.selectAll('line').data(graph.links, d => d.source + ' ' + d.target)
            .join('line');
        /* the theme drew level 3 first, so the people nearer the centre are on top */
        const order = [...nodes].sort((a, b) => b.level - a.level);
        const node = gn.selectAll('circle').data(order, d => d.id)
            .join('circle')
            .attr('class', d => cls('nodes', d))
            .attr('r', d => 30 / (d.level * d.level))
            .call(d3.drag().on('start', dragstarted).on('drag', dragged).on('end', dragended))
            .on('dblclick', (e, d) => { e.preventDefault(); location.hash = d.id; });
        node.selectAll('title').data(d => [d]).join('title').text(d => d.name);
        const text = gt.selectAll('text').data(nodes, d => d.id)
            .join('text')
            .attr('class', d => cls('texts', d))
            .attr('dy', d => -(40 / d.level))
            .attr('text-anchor', 'middle')
            .text(d => d.name)
            .on('click', (e, d) => { if (d.bio) showBio(d.id); });

        if (simulation) simulation.stop();
        simulation = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(graph.links).distance(80).id(d => d.id))
            .force('charge', d3.forceManyBody().strength(-40))
            .force('center', d3.forceCenter(...centre()))
            .on('tick', () => {
                link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
                node.attr('cx', d => d.x).attr('cy', d => d.y);
                text.attr('x', d => d.x).attr('y', d => d.y);
            });
        if (byId.get(id)[2]) showBio(id); else hideBio();
    }

    function dragstarted(e, d) {
        if (!e.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
    }
    function dragged(e, d) { d.fx = e.x; d.fy = e.y; }
    function dragended(e, d) {
        if (!e.active) simulation.alphaTarget(0);
        d.fx = null; d.fy = null;
    }

    /* the bio panel, from the person's own page (assets/js/bio-panel.js) */
    const panel = wkwBioPanel(base, { onShow: () => moveGraph('left'), onHide: () => moveGraph('centre') });
    const showBio = id => panel.show(id, byId.get(id)[1]);
    const hideBio = () => panel.hide();

    let align = 'centre';
    function centre() {
        return [align === 'left' && width > breakpoint ? width / 3 : width / 2, height / 2];
    }
    function moveGraph(dir) {
        if (align === dir) return;
        const from = centre();
        align = dir;
        const to = centre();
        d3.transition().duration(750).tween('center.move', () => {
            const i = d3.interpolateArray(from, to);
            return t => simulation.force('center', d3.forceCenter(...i(t))).alpha(Math.max(simulation.alpha(), 0.1)).restart();
        });
    }

    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            size();
            simulation.force('center', d3.forceCenter(...centre())).alpha(0.3).restart();
        }, 250);
    });

    size();
    d3.json(el.dataset.graph).then(data => {
        byId = new Map(data.nodes.map(n => [n[0], n]));
        neighbours = new Map(data.nodes.map(n => [n[0], []]));
        for (const [a, b] of data.links) {
            neighbours.get(data.nodes[a][0]).push(data.nodes[b][0]);
            neighbours.get(data.nodes[b][0]).push(data.nodes[a][0]);
        }
        const fromHash = () => decodeURIComponent(location.hash.slice(1)) || el.dataset.start;
        window.addEventListener('hashchange', () => show(fromHash()));
        show(fromHash());
    });
})();
