# Bundle for the whole-network view

`docs/network/` draws all of Who Knew Whom at once with [sigma.js](https://www.sigmajs.org/)
(WebGL) and lays it out with ForceAtlas2 from [graphology](https://graphology.github.io/). Sigma
is only published as ES modules that import other packages, so they are bundled into one file,
`docs/assets/js/vendor/sigma-bundle.min.js`, which sets `window.WKWField`.

To rebuild it, e.g. after changing the versions in `package.json`:

```bash
cd tools/field-bundle
npm install
npm run build
```

All three libraries are MIT licensed; their licence notices are at the end of the bundle.
`node_modules/` isn't in git.
