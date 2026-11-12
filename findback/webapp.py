"""Local FindBack server. Run: python -m findback.webapp."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock
from urllib.parse import urlsplit
import webbrowser

from .decision_model import Action
from .scenarios import load_scenarios
from .session import SearchSession

ROOT = Path(__file__).resolve().parent.parent
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}


class FindBackServer(ThreadingHTTPServer):
    def __init__(self, address):
        super().__init__(address, Handler)
        self.scenarios = load_scenarios()
        self.sessions = {}
        self.lock = Lock()
        self.experiments = json.loads((ROOT / 'results' / 'summary.json').read_text(encoding='utf-8'))


class Handler(BaseHTTPRequestHandler):
    def _respond(self, data, media, status=200):
        self.send_response(status)
        self.send_header('Content-Type', media)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, value, status=200):
        self._respond(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'),
                      'application/json; charset=utf-8', status)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in STATIC:
            name, media = STATIC[path]
            self._respond((ROOT / 'web' / name).read_bytes(), media)
        elif path == '/api/config':
            self._json({'scenarios': [dict(id=key, name=s.name, description=s.description, budget=s.budget,
                                           locations=[name for name, _ in s.campus.locations])
                                      for key, s in self.server.scenarios.items()],
                        'experiments': self.server.experiments})
        else:
            self._json({'error': 'Page not found.'}, 404)

    def do_POST(self):
        if self.path != '/api/session':
            self._json({'error': 'Page not found.'}, 404)
            return
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{self.headers.get("Host")}':
            self._json({'error': 'Open FindBack directly in the browser.'}, 403)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if self.headers.get_content_type() != 'application/json' or not 0 < size <= 512_000:
                raise ValueError('Expected a valid search request.')
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError('Expected a JSON object.')
            with self.server.lock:
                result = self._operate(payload)
                response = json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self._respond(response, 'application/json; charset=utf-8')
        except (ValueError, KeyError, TypeError) as exc:
            self._json({'error': str(exc)}, 400)

    def _operate(self, p):
        operation = p['operation']
        token = p.get('session')
        sessions = self.server.sessions
        if operation in ('start', 'restore'):
            settings = p['settings'] if operation == 'restore' else p
            scenario_id = settings['scenario']
            scenario = self.server.scenarios[scenario_id]
            session = SearchSession(scenario, settings['item'], settings['mode'], settings['seed'],
                                    settings['depth'], settings['budget'], settings.get('start_at', ''),
                                    settings.get('last_seen', ''), settings.get('description', ''))
            if operation == 'restore':
                session.replay(p['events'])
            sessions.pop(token, None)
            token = token_urlsafe(24)
            sessions[token] = (session, scenario_id)
            if len(sessions) > 24:
                del sessions[next(iter(sessions))]
        else:
            if token not in sessions:
                raise ValueError('Session expired. Start a new search.')
            session, scenario_id = sessions[token]
            if p.get('revision') != session.revision:
                raise ValueError('This search changed in another request. Refresh or start a new search.')
            if session.revision >= 200:
                raise ValueError('This search has reached its history limit. Start a new search.')
            if operation == 'action':
                session.apply(Action(p['kind'], p.get('target', '')), p.get('outcome'))
            elif operation == 'report':
                session.report(p['target'], p['outcome'], p['report_id'], p.get('note', ''))
            elif operation == 'toggle':
                session.toggle_cell(p['row'], p['col'])
            else:
                raise ValueError('Unknown operation.')
        return {'session': token, 'scenario_id': scenario_id, 'state': session.snapshot()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--open', action='store_true', help='open the default browser')
    args = parser.parse_args()
    with FindBackServer(('127.0.0.1', args.port)) as server:
        url = f'http://127.0.0.1:{server.server_port}/'
        print(f'FindBack is running at {url}', flush=True)
        if args.open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
