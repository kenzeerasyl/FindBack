'use strict';

const runtimeBase = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
let engine;

async function loadEngine() {
  importScripts(runtimeBase + 'pyodide.js');
  const [python, response] = await Promise.all([
    loadPyodide({indexURL: runtimeBase}),
    fetch('./findback-engine.zip'),
  ]);
  if (!response.ok) throw new Error('Не удалось загрузить данные кампуса.');
  python.unpackArchive(await response.arrayBuffer(), 'zip', {extractDir: '/findback_app'});
  python.runPython([
    'import json, sys',
    'sys.path.insert(0, "/findback_app")',
    'from findback.service import SearchService',
    'service = SearchService("/findback_app")',
  ].join('\n'));
  return python;
}

self.addEventListener('message', async ({data}) => {
  try {
    if (!engine) engine = loadEngine();
    const python = await engine;
    let body;
    if (data.path === '/api/config') {
      body = python.runPython('json.dumps(service.config(), ensure_ascii=False, allow_nan=False)');
    } else if (data.path === '/api/session') {
      python.globals.set('request_body', data.body);
      try {
        body = python.runPython('json.dumps(service.operate(json.loads(request_body)), ensure_ascii=False, allow_nan=False)');
      } finally {
        python.globals.delete('request_body');
      }
    } else {
      throw new Error('Unknown request.');
    }
    self.postMessage({id: data.id, ok: true, body: JSON.parse(body)});
  } catch (error) {
    const message = String(error.message || error).trim().split('\n').at(-1);
    const prefix = /^(ValueError|KeyError|TypeError): /;
    self.postMessage({id: data.id, ok: false, body: {error: message.replace(prefix, '')}});
  }
});
