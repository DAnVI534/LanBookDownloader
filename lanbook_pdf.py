#!/usr/bin/env python3
"""
lanbook_pdf.py - скачивает книгу с e.lanbook.com одним PDF-файлом.

Как это работает: читалка отдаёт документ запросом
    https://reader.lanbook.com/api/v2/book/<ID>/documentFile?base64=1&lms=&jwtToken=...
в ответ приходит JSON {"data": "<PDF в base64>"}. Скрипт скачивает этот ответ,
достаёт поле data и сохраняет настоящий PDF.

Использование:
    python lanbook_pdf.py                      (адрес спросит сам)
    python lanbook_pdf.py "<Request URL>"      (адрес аргументом, в кавычках)
    python lanbook_pdf.py --out my_book.pdf

Токен jwtToken в адресе живёт недолго: копируйте адрес и сразу запускайте.
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def load_headers(config_path):
    headers = {
        "Referer": "https://e.lanbook.com/",
        "User-Agent": USER_AGENT,
    }
    if config_path and os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                headers.update(json.load(f))
        except Exception as e:
            print(f"Предупреждение: не удалось прочитать {config_path}: {e}", file=sys.stderr)
    return headers


def fetch_with_curl(url, headers):
    """Скачивает через curl. На Windows отключает проверку отзыва сертификата
    (иначе schannel часто падает с CRYPT_E_NO_REVOCATION_CHECK)."""
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        return None
    fd, tmp = tempfile.mkstemp(suffix=".bin")
    os.close(fd)
    cmd = [curl, "-sS", "-L", "--fail", "--max-time", "300", "-o", tmp]
    if os.name == "nt":
        cmd.append("--ssl-no-revoke")
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print("curl:", (res.stderr or "").strip()[:300], file=sys.stderr)
            return None
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def fetch_with_requests(url, headers):
    try:
        import requests
    except ImportError:
        return None
    try:
        r = requests.get(url, headers=headers, timeout=300)
    except Exception as e:
        print("requests:", str(e)[:300], file=sys.stderr)
        return None
    if not r.ok:
        print(f"requests: HTTP {r.status_code}", file=sys.stderr)
        return None
    return r.content


def extract_pdf(raw):
    """Принимает ответ сервера, возвращает байты PDF."""
    if raw.startswith(b"%PDF"):
        return raw
    # JSON-обёртка {"data": "<base64>"}
    try:
        obj = json.loads(raw.decode("utf-8"))
        if isinstance(obj, dict) and "data" in obj:
            pdf = base64.b64decode(obj["data"])
            if pdf.startswith(b"%PDF"):
                return pdf
    except Exception:
        pass
    # просто base64 без обёртки
    try:
        pdf = base64.b64decode(raw)
        if pdf.startswith(b"%PDF"):
            return pdf
    except Exception:
        pass
    return None


def main():
    p = argparse.ArgumentParser(description="Скачать книгу e.lanbook.com в PDF")
    p.add_argument("url", nargs="?", help="Request URL запроса documentFile из DevTools")
    p.add_argument("--out", help="имя выходного PDF (по умолчанию book_<ID>.pdf)")
    p.add_argument("--config", default="header.json",
                   help="необязательный json с доп. заголовками, например Cookie")
    args = p.parse_args()

    url = (args.url or input("Вставьте Request URL (documentFile?...jwtToken=...): ")).strip().strip('"')
    if "documentFile" not in url:
        print("Ошибка: это не адрес documentFile. Нужен запрос вида "
              "https://reader.lanbook.com/api/v2/book/<ID>/documentFile?base64=1&lms=&jwtToken=...",
              file=sys.stderr)
        sys.exit(1)

    m = re.search(r"/book/(\d+)/", url)
    book_id = m.group(1) if m else "unknown"
    out = args.out or f"book_{book_id}.pdf"

    headers = load_headers(args.config)

    print("Скачиваю...")
    raw = fetch_with_curl(url, headers)
    if raw is None:
        raw = fetch_with_requests(url, headers)
    if raw is None:
        print("Не удалось скачать. Проверьте VPN/сеть и что токен свежий "
              "(скопируйте адрес заново).", file=sys.stderr)
        sys.exit(2)

    pdf = extract_pdf(raw)
    if pdf is None:
        print("Ответ сервера не похож на PDF. Начало ответа:", file=sys.stderr)
        print(raw[:200].decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(3)

    with open(out, "wb") as f:
        f.write(pdf)
    print(f"Готово: {out} ({len(pdf) / 1024:.0f} КБ)")


if __name__ == "__main__":
    main()
