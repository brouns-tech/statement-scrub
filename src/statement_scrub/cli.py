import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Local reviewed financial-document sanitisation")
    sub = parser.add_subparsers(dest='command', required=True)
    ui = sub.add_parser('ui', help='Start the local review UI')
    ui.add_argument('--port', type=int, default=8501)
    demo = sub.add_parser('demo', help='Write a wholly fabricated input PDF for trying the UI')
    demo.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'demo':
        from statement_scrub.demo import demo_pdf
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite an original or existing result.
        with args.output.open('xb') as target:
            target.write(demo_pdf())
        print('Fabricated demo created.')
        return
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535.')
    env = os.environ.copy()
    app = Path(__file__).with_name('ui.py')
    # Explicit flags override any local Streamlit config. No config file is committed or generated.
    raise SystemExit(subprocess.call([
        sys.executable, '-m', 'streamlit', 'run', str(app),
        '--server.address=127.0.0.1', f'--server.port={args.port}',
        '--server.headless=true', '--theme.primaryColor=#2563EB', '--browser.gatherUsageStats=false',
        '--server.fileWatcherType=none', '--server.maxUploadSize=30',
        '--server.enableXsrfProtection=true', '--server.enableCORS=true',
    ], env=env))
