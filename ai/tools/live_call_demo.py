"""Phát một file âm thanh qua API cuộc gọi trực tiếp của backend, đúng tốc độ thời gian thực, và in các sự kiện.

Dùng để thử và trình diễn phân tích cuộc gọi trực tiếp khi chưa có ứng dụng VoIP: script đóng vai ứng dụng mobile.

    pip install websockets
    python live_call_demo.py --audio call.raw --email test@example.com --password ...

``--audio`` là PCM 16 bit, 16 kHz, một kênh, không có header. Tạo từ file bất kỳ bằng:

    ffmpeg -i call.m4a -f s16le -ar 16000 -ac 1 call.raw

Ghi âm thường trộn hai bên vào một kênh, nên cả file được gửi như tiếng của người gọi (``--speaker caller``).
"""

import argparse
import asyncio
import json
import time
import urllib.error
import urllib.request

import websockets

SAMPLE_RATE = 16_000
PACKET_SECONDS = 0.2


def request(base: str, method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    """Gọi một API JSON của backend."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    call = urllib.request.Request(base + path, data=data, method=method)
    call.add_header("Content-Type", "application/json")
    if token:
        call.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(call, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{method} {path} -> {error.code}: {error.read().decode('utf-8', 'replace')}") from None


async def run(args: argparse.Namespace) -> None:
    """Đăng nhập, mở cuộc gọi trực tiếp, phát âm thanh và in sự kiện cho tới khi có kết quả cuối."""
    base = args.backend.rstrip("/")
    credentials = {"email": args.email, "password": args.password}
    try:
        token = request(base, "POST", "/api/v1/auth/login", body=credentials)["accessToken"]
    except SystemExit:
        token = request(base, "POST", "/api/v1/auth/register", body=credentials | {"fullName": "Live demo"})["accessToken"]

    opened = request(base, "POST", "/api/v1/live-calls", token, {})
    print(f"opened live call {opened['callId']} (analysis {opened['analysisId']})")
    url = base.replace("http", "ws", 1) + opened["streamPath"] + "?ticket=" + opened["ticket"]
    pcm = open(args.audio, "rb").read()
    if args.seconds:
        pcm = pcm[:int(args.seconds * SAMPLE_RATE) * 2]
    prefix = b"\x00" if args.speaker == "caller" else b"\x01"
    packet = int(PACKET_SECONDS * SAMPLE_RATE) * 2

    async with websockets.connect(url, max_size=None) as socket:
        started = time.monotonic()

        async def send() -> None:
            for index, start in enumerate(range(0, len(pcm), packet)):
                # Gửi đúng nhịp thời gian thực (hoặc nhanh hơn theo --speed), như micro của một cuộc gọi thật.
                await asyncio.sleep(max(0.0, started + index * PACKET_SECONDS / args.speed - time.monotonic()))
                await socket.send(prefix + pcm[start:start + packet])
            await socket.send(json.dumps({"type": "end"}))
            print(f"[{time.monotonic() - started:6.1f}s] sent all audio ({len(pcm) / 2 / SAMPLE_RATE:.0f}s) and end")

        sender = asyncio.create_task(send())
        async for message in socket:
            event = json.loads(message)
            clock = time.monotonic() - started
            kind = event["type"]
            if kind == "transcript":
                # Độ trễ: câu nói kết thúc ở giây nào của cuộc gọi, và chữ về tới ứng dụng lúc nào.
                lag = clock * args.speed - event["end"]
                print(f"[{clock:6.1f}s] {event['speaker']:6} {event['start']:6.1f}-{event['end']:6.1f}s "
                      f"(+{lag:4.1f}s) {event['text'][:110]}")
            elif kind == "risk":
                print(f"[{clock:6.1f}s]        risk {event['riskScore']:3} {event['riskLevel']:6} {event['indicators']}")
            elif kind == "alert":
                print(f"[{clock:6.1f}s] >>>>>> ALERT {event['riskLevel']} ({event['riskScore']}) "
                      f"at {event['atSeconds']}s of the call: {event['triggeredBy']['text'][:90]}")
            elif kind == "final":
                print(f"[{clock:6.1f}s] FINAL {event['riskLevel']} {event['riskScore']} confidence={event['confidence']} "
                      f"indicators={event['indicators']} turns={len(event['turns'])} endedBy={event['endedBy']}")
            else:
                print(f"[{clock:6.1f}s] {kind}: {json.dumps(event, ensure_ascii=False)[:200]}")
        await sender

    stored = request(base, "GET", f"/api/v1/calls/{opened['callId']}/analyses/latest", token)
    call = request(base, "GET", f"/api/v1/calls/{opened['callId']}", token)
    print(f"stored: status={stored['status']} errorCode={stored['errorCode']} riskLevel={stored['riskLevel']} "
          f"riskScore={stored['riskScore']} transcriptWords={len((stored['transcript'] or '').split())} "
          f"source={call['source']} audio={call['audio'] and (call['audio']['contentType'], call['audio']['durationSeconds'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", default="http://127.0.0.1:8080")
    parser.add_argument("--audio", required=True, help="raw PCM s16le, 16 kHz, mono")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--speaker", choices=("caller", "callee"), default="caller")
    parser.add_argument("--seconds", type=float, default=0, help="only play the first N seconds")
    parser.add_argument("--speed", type=float, default=1.0, help="1.0 is real time")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
