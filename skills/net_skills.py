"""
Мрежа и интернет: IP адрес, скорост на интернета, пинг, работи ли сайт, Wi-Fi, локалната мрежа,
кой процес е заел порт, DNS и контейнерите в Docker.
"""
import re
import socket
import subprocess
import time
import urllib.request

from jarvis import geo, jarvis_tool

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(args: list[str], timeout: float = 20) -> str:
    result = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    raw = result.stdout or result.stderr
    for encoding in ("utf-8", "cp866", "cp1251"):  # конзолните програми на Windows пишат в различни кодировки
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


@jarvis_tool
def my_public_ip() -> str:
    """Публичният IP адрес на интернета на сър, доставчикът и приблизителното място."""
    data = geo.get_json("http://ip-api.com/json/?fields=status,query,isp,city,country")
    if data.get("status") != "success":
        raise ConnectionError("услугата за IP не отговаря")
    return f"Публичен IP: {data['query']} ({data.get('isp', '')}, {data.get('city', '')}, {data.get('country', '')})."


@jarvis_tool
def internet_speed_test() -> str:
    """Измерва скоростта на интернета (изтегляне) и забавянето (пинг) — отнема около 10 секунди."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}  # без него Cloudflare отказва
    started = time.monotonic()
    urllib.request.urlopen(urllib.request.Request("https://speed.cloudflare.com/__down?bytes=1000", headers=headers),
                           timeout=10).read()
    latency = (time.monotonic() - started) * 1000
    total, started = 0, time.monotonic()
    request = urllib.request.Request("https://speed.cloudflare.com/__down?bytes=50000000", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        while chunk := response.read(262144):
            total += len(chunk)
            if time.monotonic() - started > 8:  # стига ни — не харчим излишно трафик
                break
    seconds = time.monotonic() - started
    mbps = total * 8 / seconds / 1e6
    verdict = "отлично" if mbps > 100 else "добре" if mbps > 30 else "бавничко" if mbps > 10 else "бавно"
    return f"Изтегляне: {mbps:.0f} Mbps ({verdict}), забавяне около {latency:.0f} ms."


@jarvis_tool
def ping_host(host: str = "google.com") -> str:
    """Проверява връзката до сайт или сървър (пинг) — отговаря ли и колко бързо.

    Args:
        host: Адрес или IP, напр. "google.com" или "192.168.1.1".
    """
    host = re.sub(r"^https?://", "", host.strip()).split("/")[0]
    output = _run(["ping", "-n", "4", host], timeout=25)
    times = [int(t) for t in re.findall(r"[=<](\d+)\s*ms", output)]
    if not times:
        return f"{host} не отговаря на пинг (или не съществува)."
    return f"{host} отговаря: средно {sum(times) / len(times):.0f} ms (от {min(times)} до {max(times)} ms), {len(times)}/4 отговора."


@jarvis_tool
def website_status(url: str) -> str:
    """Работи ли даден сайт в момента и колко бързо отговаря.

    Args:
        url: Адресът, напр. "abv.bg".
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    started = time.monotonic()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            code = response.status
    except urllib.error.HTTPError as e:
        code = e.code
    except (urllib.error.URLError, OSError) as e:
        return f"{url} не работи или не е достъпен ({getattr(e, 'reason', e)})."
    ms = (time.monotonic() - started) * 1000
    state = "работи" if code < 400 else "отговаря с грешка"
    return f"{url} {state} (код {code}), отговори за {ms:.0f} ms."


@jarvis_tool
def local_network_info() -> str:
    """Локалната мрежа: IP адресите на компютъра и връзките (кабел, Wi-Fi)."""
    import psutil
    stats = psutil.net_if_stats()
    parts = []
    for name, addresses in psutil.net_if_addrs().items():
        ips = [a.address for a in addresses if a.family == socket.AF_INET and not a.address.startswith("127.")]
        if ips and stats.get(name) and stats[name].isup:
            speed = f", {stats[name].speed} Mbps" if stats[name].speed else ""
            parts.append(f"{name}: {', '.join(ips)}{speed}")
    return "Мрежови връзки: " + ("; ".join(parts) or "няма активни") + "."


@jarvis_tool
def wifi_info() -> str:
    """Към коя Wi-Fi мрежа е свързан компютърът и колко е силен сигналът."""
    output = _run(["netsh", "wlan", "show", "interfaces"])
    ssid = re.search(r"^\s*SSID\s*:\s*(.+)$", output, re.MULTILINE)
    signal = re.search(r"(\d+)%", output)
    if not ssid:
        return "Компютърът не е свързан към Wi-Fi (вероятно е на кабел)."
    return f"Wi-Fi: {ssid[1].strip()}" + (f", сигнал {signal[1]}%." if signal else ".")


@jarvis_tool
def port_in_use(port: int) -> str:
    """Коя програма е заела даден порт (напр. 3000, 8080, 5432) — за програмисти.

    Args:
        port: Номерът на порта.
    """
    import psutil
    users = []
    for conn in psutil.net_connections(kind="inet"):
        if conn.laddr and conn.laddr.port == port and conn.status in ("LISTEN", "NONE"):
            try:
                name = psutil.Process(conn.pid).name() if conn.pid else "системата"
            except psutil.Error:
                name = f"процес {conn.pid}"
            users.append(f"{name} (PID {conn.pid}, {conn.laddr.ip})")
    return f"Порт {port} е зает от: {', '.join(dict.fromkeys(users))}." if users else f"Порт {port} е свободен."


@jarvis_tool
def dns_lookup(domain: str) -> str:
    """Кои IP адреси има даден домейн (DNS).

    Args:
        domain: Домейнът, напр. "google.com".
    """
    domain = re.sub(r"^https?://", "", domain.strip()).split("/")[0]
    name, aliases, ips = socket.gethostbyname_ex(domain)
    return f"{domain}: {', '.join(ips)}" + (f" (основно име {name})" if name != domain else "") + "."


@jarvis_tool
def docker_containers() -> str:
    """Кои Docker контейнери работят (за програмисти)."""
    try:
        output = _run(["docker", "ps", "--format", "{{.Names}} — {{.Status}} ({{.Image}})"], timeout=15)
    except FileNotFoundError:
        return "Docker не е инсталиран."
    if any(word in output.lower() for word in ("error", "cannot connect", "failed to connect")):
        return "Docker не е пуснат (стартирайте Docker Desktop)."
    lines = [ln for ln in output.splitlines() if ln.strip()]
    return ("Работещи контейнери: " + "; ".join(lines) + ".") if lines else "Няма работещи контейнери."
