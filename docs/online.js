'use strict';

{
  let worker;
  let nextId = 0;
  const pending = new Map();

  function handleWorkerError() {
    for (const request of pending.values()) {
      clearTimeout(request.timer);
      request.reject(new Error('Не удалось запустить вычисления FindBack.'));
    }
    pending.clear();
    worker?.terminate();
    worker = undefined;
  }

  globalThis.findbackRequest = (path, options = {}) => {
    if (!worker) {
      worker = new Worker(new URL('./engine-worker.js', document.baseURI));
      worker.addEventListener('message', ({data}) => {
        const request = pending.get(data.id);
        if (!request) return;
        clearTimeout(request.timer);
        pending.delete(data.id);
        request.resolve({ok: data.ok, json: async () => data.body});
      });
      worker.addEventListener('error', handleWorkerError);
    }
    return new Promise((resolve, reject) => {
      const id = ++nextId;
      const timer = setTimeout(handleWorkerError, 45000);
      pending.set(id, {resolve, reject, timer});
      worker.postMessage({id, path, body: options.body});
    });
  };
}
