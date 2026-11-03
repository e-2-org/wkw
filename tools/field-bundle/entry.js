// The libraries the whole-network view (docs/assets/js/network.js) uses, as one global.
import Graph from 'graphology';
import Sigma from 'sigma';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import FA2Layout from 'graphology-layout-forceatlas2/worker';

window.WKWField = { Graph, Sigma, forceAtlas2, FA2Layout };
