"""Bounded network measurements; never deploys, installs or changes configuration."""
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request

LIMIT = 1024 * 1024


def emit(item):
    print(json.dumps(item, ensure_ascii=False), flush=True)


def download(label, url):
    started = time.monotonic()
    result = {'test': label, 'url': url, 'bytes': 0}
    try:
        req = urllib.request.Request(url, headers={'Range': f'bytes=0-{LIMIT-1}', 'User-Agent': 'wardrobe-network-diagnostic/1'})
        with urllib.request.urlopen(req, timeout=10) as response:
            result['http_status'] = response.status
            result['content_range'] = response.headers.get('Content-Range')
            while result['bytes'] < LIMIT and time.monotonic() - started < 20:
                data = response.read(min(65536, LIMIT-result['bytes']))
                if not data:
                    break
                result['bytes'] += len(data)
        result['status'] = ('byte_limit_reached' if result['bytes'] == LIMIT else 'time_limited_sample') if result['bytes'] else 'empty'
    except Exception as exc:
        result['status'] = 'error'
        result['error'] = str(exc)
    result['seconds'] = round(time.monotonic()-started, 3)
    result['KiB_per_second'] = round(result['bytes']/1024/max(result['seconds'], .001), 2)
    return result


def download_checks(domestic=False):
    if domestic:
        results = []
        for protocol in ('http', 'https'):
            results.append(download('tencent_debian_'+protocol, protocol+'://mirrors.cloud.tencent.com/debian/dists/trixie/main/binary-amd64/Packages.xz'))
            emit(results[-1])
        results.append(download('tencent_pypi_index', 'https://mirrors.cloud.tencent.com/pypi/simple/fastapi/'))
        emit(results[-1])
        try:
            emit({'tencent_mirror_resolved_ips': sorted({x[4][0] for x in socket.getaddrinfo('mirrors.cloud.tencent.com', 443)})})
        except OSError as exc:
            emit({'dns_error': str(exc)})
        return results
    results = []
    for protocol in ('http', 'https'):
        results.append(download('debian_'+protocol, protocol+'://deb.debian.org/debian/dists/trixie/main/binary-amd64/Packages.xz'))
        emit(results[-1])
    # Discover the actual official wheel URL rather than guessing a CDN path.
    try:
        with urllib.request.urlopen('https://pypi.org/pypi/fastapi/0.142.1/json', timeout=10) as response:
            metadata = json.load(response)
        wheel = next(x['url'] for x in metadata['urls'] if x['packagetype']=='bdist_wheel')
        if not wheel.startswith('https://files.pythonhosted.org/'):
            raise ValueError('Unexpected wheel origin')
        results.append(download('pypi_wheel', wheel))
    except Exception as exc:
        results.append({'test': 'pypi_wheel', 'status': 'error', 'error': str(exc)})
    emit(results[-1])
    return results


def command(argv, *, timeout=30, data=None):
    started = time.monotonic()
    process = subprocess.Popen(argv, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    timed_out = False
    try:
        stdout, stderr = process.communicate(data, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
    return {'exit_code': process.returncode, 'timed_out': timed_out,
            'seconds': round(time.monotonic()-started, 3),
            'stdout': stdout.decode(errors='replace')[-12000:], 'stderr': stderr.decode(errors='replace')[-12000:]}


def ssh(script, **kwargs):
    return command(['ssh', 'diagnostic', script], **kwargs)


def run(output, domestic=False):
    results = {'runner_downloads': [], 'transfers': []}
    remote = None
    try:
        results['runner_ssh'] = command(['ssh', '-V'])
        results['server_snapshot'] = ssh('uname -m; uptime; df -h /tmp; free -m; command -v vmstat >/dev/null && vmstat 1 2; ssh -V 2>&1; peer=${SSH_CONNECTION%% *}; ip route get "$peer"', timeout=20)
        emit({'server_snapshot': results['server_snapshot']})
        create = ssh('mktemp -d /tmp/wardrobe-netcheck.XXXXXXXX')
        candidate = create['stdout'].strip()
        if create['exit_code'] or not candidate.startswith('/tmp/wardrobe-netcheck.') or not candidate.replace('/tmp/wardrobe-netcheck.', '').isalnum():
            raise RuntimeError('Unable to create safe diagnostic directory: '+create['stderr'])
        remote = candidate
        with tempfile.TemporaryDirectory() as local:
            local = Path(local)
            payload = os.urandom(LIMIT)
            sample = local/'sample.bin'; sample.write_bytes(payload)
            tiny = local/'tiny.bin';tiny.write_bytes(payload[:16384])
            for label, argv, data, size in ([] if domestic else [
                ('sftp_16KiB', ['scp', str(tiny), f'diagnostic:{remote}/sftp_16KiB.bin'], None, 16384),
                ('sftp_1MiB', ['scp', str(sample), f'diagnostic:{remote}/sftp_1MiB.bin'], None, LIMIT),
                ('legacy_scp_1MiB', ['scp', '-O', str(sample), f'diagnostic:{remote}/legacy_scp_1MiB.bin'], None, LIMIT),
                ('ssh_stream_1MiB', ['ssh', 'diagnostic', f'cat > {shlex.quote(remote+"/ssh_stream_1MiB.bin")}'], payload, LIMIT),
            ]):
                emit({'starting': label, 'byte_limit': size, 'timeout_seconds': 60})
                measured = command(argv, timeout=60, data=data)
                actual = ssh(f'stat -c %s {shlex.quote(remote+"/"+label+".bin")} 2>/dev/null || echo 0')
                received = int(actual['stdout'].strip()) if actual['stdout'].strip().isdigit() else None
                measured.update(test=label, expected_bytes=size, received_bytes=received,
                                KiB_per_second=round((received or 0)/1024/max(measured['seconds'], .001), 2))
                results['transfers'].append(measured);emit(measured)
            results['server_tcp_after_transfers'] = ssh('peer=${SSH_CONNECTION%% *}; ss -tin dst "$peer"', timeout=15)
            # Copy only this small diagnostic script, not the application or its config.
            copied = command(['scp', str(Path(__file__).resolve()), f'diagnostic:{remote}/probe.py'], timeout=30)
            if copied['exit_code'] or copied['timed_out']:
                results['server_downloads'] = {'status': 'script_copy_failed', 'detail': copied}
            else:
                results['server_downloads'] = ssh(f'python3 {shlex.quote(remote+"/probe.py")} --downloads'+(' --domestic' if domestic else ''), timeout=90)
                # Test cached Docker base only; explicitly prohibit pulling another image.
                container = f'if docker image inspect python:3.12-slim >/dev/null 2>&1; then docker run --rm --pull=never --network bridge --mount type=bind,src={remote}/probe.py,dst=/probe.py,readonly python:3.12-slim python /probe.py --downloads; else echo "SKIPPED: Python base image is not present in Docker image store; build cache does not guarantee a runnable image."; fi'
                results['container_downloads'] = {'status': 'not_repeated_in_domestic_followup'} if domestic else ssh(container, timeout=90)
                emit({'server_downloads': results['server_downloads'], 'container_downloads': results['container_downloads']})
        results['runner_downloads'] = download_checks(domestic)
    except Exception as exc:
        results['diagnostic_error'] = str(exc);emit({'diagnostic_error': str(exc)})
    finally:
        if remote:
            results['cleanup'] = ssh('rm -rf -- '+shlex.quote(remote), timeout=20)
        Path(output).write_text(json.dumps(results, ensure_ascii=False, indent=2))
        emit({'report_saved': str(output)})


def service_checks(output):
    remote = "docker ps --filter label=com.docker.compose.project=wardrobe-lab --format '{{.Names}} {{.Status}} {{.Ports}}'; ss -lnt; python3 -c \"import urllib.request; r=urllib.request.urlopen('http://127.0.0.1/healthz',timeout=5); print('LOCAL_CADDY_HTTP',r.status,r.read().decode())\""
    results = {'server_service': ssh(remote, timeout=25)}
    host = os.environ.get('DIAGNOSTIC_HOST', '')
    if host and all(c.isalnum() or c in '.-' for c in host):
        results['public_http'] = command(['curl','--fail','--connect-timeout','10','--max-time','20','http://'+host+'/healthz'],timeout=25)
    Path(output).write_text(json.dumps(results,ensure_ascii=False,indent=2))
    emit(results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--downloads', action='store_true')
    parser.add_argument('--domestic', action='store_true')
    parser.add_argument('--service', action='store_true')
    parser.add_argument('--output', default='network-diagnostic.json')
    args = parser.parse_args()
    if args.service:
        service_checks(args.output)
    elif args.downloads:
        download_checks(args.domestic)
    else:
        run(args.output, args.domestic)
